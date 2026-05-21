"""Servico de integracao com webhook do n8n para disparo de workflows de contestacao.

Refatorado na Etapa 5:
- Os 3 fluxos (contestacao, edicao, peticao) compartilhavam ~40 linhas de
  POST+headers+retry+parse. Foi extraido `_invocar_webhook(...)` parametrizado
  por `parse_response`/`label`/`vazio_fatal`. As tres funcoes publicas viraram
  one-liners que so configuram o webhook URL e a politica de erro.
- Eliminou duplicacao de construcao de Request + tratamento de erros.
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_N8N_WEBHOOK_URL = "http://localhost:5678/webhook/contestacao-claude"
DEFAULT_N8N_EDICAO_WEBHOOK_URL = "http://localhost:5678/webhook/editar-contestacao"
DEFAULT_N8N_PETICAO_WEBHOOK_URL = "http://localhost:5678/webhook/contestar-por-peticao"
N8N_TIMEOUT_SECONDS = int(os.getenv("N8N_TIMEOUT_SECONDS", "60"))

# PR8 P1.1 — retry com backoff exponencial para tolerar cold-start/reinicio do n8n.
N8N_MAX_RETRIES = int(os.getenv("N8N_MAX_RETRIES", "3"))
N8N_RETRY_BACKOFF_BASE = float(os.getenv("N8N_RETRY_BACKOFF_SECONDS", "1.0"))

# Tipos de excecao de rede tratadas como "erro temporario" do n8n (alvo do retry
# e de mapeamento para N8NServiceError no caller).
_REDE_ERRORS = (HTTPError, URLError, TimeoutError, OSError)


class N8NServiceError(Exception):
    pass


# ─────────────────────────── Configuracao de URLs ────────────────────────────


def _get_webhook_url(env_var: str, default: str) -> str:
    return os.getenv(env_var, default).strip() or default


def get_n8n_webhook_url() -> str:
    return _get_webhook_url("N8N_WEBHOOK_URL", DEFAULT_N8N_WEBHOOK_URL)


def get_n8n_edicao_webhook_url() -> str:
    return _get_webhook_url("N8N_EDICAO_WEBHOOK_URL", DEFAULT_N8N_EDICAO_WEBHOOK_URL)


def get_n8n_peticao_webhook_url() -> str:
    return _get_webhook_url("N8N_WEBHOOK_PETICAO", DEFAULT_N8N_PETICAO_WEBHOOK_URL)


def get_n8n_webhook_auth_token() -> str:
    return os.getenv("N8N_WEBHOOK_AUTH_TOKEN", "").strip()


# ───────────────────────────── Retry com backoff ─────────────────────────────


def _enviar_com_retry(request: Request, timeout: int, label: str) -> bytes:
    """Tenta N8N_MAX_RETRIES vezes com backoff exponencial antes de levantar.

    `label` aparece nos logs (ex: "contestacao", "edicao", "peticao") para
    distinguir qual fluxo falhou no observability.
    """
    last_error: Exception | None = None
    for attempt in range(1, N8N_MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except _REDE_ERRORS as error:
            last_error = error
            if attempt < N8N_MAX_RETRIES:
                wait = N8N_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "n8n %s tentativa %d/%d falhou (%s). Aguardando %.1fs antes do retry.",
                    label,
                    attempt,
                    N8N_MAX_RETRIES,
                    type(error).__name__,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "n8n %s falhou em todas as %d tentativas (%s: %s)",
                    label,
                    N8N_MAX_RETRIES,
                    type(error).__name__,
                    error,
                )
    # Por contrato N8N_MAX_RETRIES >= 1 entao last_error nunca e None aqui.
    raise last_error  # type: ignore[misc]


# ─────────────────── Montagem do Request HTTP (compartilhada) ────────────────


def _montar_request(url: str, dados: dict[str, Any]) -> Request:
    """Constroi Request POST com auth opcional e body JSON."""
    headers = {"Content-Type": "application/json"}
    auth_token = get_n8n_webhook_auth_token()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    return Request(
        url=url,
        data=json.dumps(dados).encode("utf-8"),
        headers=headers,
        method="POST",
    )


# ───────────────────────── Invocacao parametrizada ───────────────────────────


def _invocar_webhook(
    *,
    webhook_url: str,
    dados: dict[str, Any],
    label: str,
    parse_response: Callable[[bytes, str], Any],
    vazio_fatal: bool,
    mensagem_vazio: str = "",
) -> Any:
    """Executa POST + retry + parse para qualquer fluxo n8n.

    Parametros:
    - `parse_response(body_bytes, label) -> Any`: estrategia de parse do payload
      (cada fluxo trata respostas vazias/nao-JSON de jeito diferente).
    - `vazio_fatal`: se True, body vazio levanta N8NServiceError; se False,
      devolve fallback (caso historico do fluxo principal).
    - `mensagem_vazio`: mensagem usada quando `vazio_fatal=True` e body vier vazio.
    """
    request = _montar_request(webhook_url, dados)

    try:
        response_body = _enviar_com_retry(request, N8N_TIMEOUT_SECONDS, label)
    except _REDE_ERRORS as error:
        raise N8NServiceError(
            f"Falha ao acionar o n8n em {webhook_url}. Verifique se o workflow esta ativo."
        ) from error

    if not response_body:
        logger.warning("n8n (%s) respondeu sem corpo em %s", label, webhook_url)
        if vazio_fatal:
            raise N8NServiceError(mensagem_vazio)
        return {"message": "Workflow acionado sem corpo de resposta."}

    return parse_response(response_body, webhook_url)


# ─────────────────────────── Estrategias de parse ────────────────────────────


def _parse_contestacao(response_body: bytes, webhook_url: str) -> Any:
    """Parse tolerante: payload nao-JSON vira raw_response, dict valida schema."""
    try:
        raw = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning(
            "n8n retornou payload nao-JSON de %s: %s",
            webhook_url,
            type(error).__name__,
        )
        return {
            "status": "processando",
            "raw_response": response_body.decode("utf-8", errors="replace"),
        }

    if isinstance(raw, dict):
        return _validar_schema_contestacao(raw)
    return raw


def _validar_schema_contestacao(raw: dict[str, Any]) -> dict[str, Any]:
    """Filtra campos desconhecidos via Pydantic para prevenir injecao arbitraria."""
    from App.models.n8n_response import N8NResponse

    try:
        return N8NResponse(**raw).model_dump(exclude_none=True)
    except Exception:  # noqa: BLE001 - Pydantic levanta ValidationError generico
        logger.warning(
            "Resposta n8n nao passou na validacao de schema — retornando status padrao"
        )
        return {"status": "processando"}


def _parse_estrito(rotulo_humano: str) -> Callable[[bytes, str], Any]:
    """Cria um parser que levanta N8NServiceError em payload nao-JSON.

    Usado pelos fluxos `edicao` e `peticao`: o workflow E obrigado a devolver
    JSON valido; payload corrompido e contrato quebrado.
    """

    def parse(response_body: bytes, webhook_url: str) -> Any:
        try:
            return json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.warning(
                "n8n (%s) retornou payload nao-JSON de %s: %s",
                rotulo_humano,
                webhook_url,
                type(error).__name__,
            )
            raise N8NServiceError(
                f"Workflow de {rotulo_humano} retornou resposta nao-JSON."
            ) from error

    return parse


# ─────────────────────────── Fluxos sincronos ────────────────────────────────


def _enviar_para_n8n_sync(dados: dict[str, Any], webhook_url: str | None = None) -> Any:
    """Fluxo principal de contestacao. Tolerante a corpo vazio / nao-JSON."""
    return _invocar_webhook(
        webhook_url=webhook_url or get_n8n_webhook_url(),
        dados=dados,
        label="contestacao",
        parse_response=_parse_contestacao,
        vazio_fatal=False,
    )


def _enviar_para_n8n_edicao_sync(dados: dict[str, Any]) -> Any:
    """Fluxo de edicao. Espera JSON com `substituicoes` + `campos_ausentes`."""
    return _invocar_webhook(
        webhook_url=get_n8n_edicao_webhook_url(),
        dados=dados,
        label="edicao",
        parse_response=_parse_estrito("edicao"),
        vazio_fatal=True,
        mensagem_vazio="Workflow de edicao retornou resposta vazia.",
    )


def _enviar_para_n8n_peticao_sync(dados: dict[str, Any]) -> Any:
    """Fluxo contestar-por-peticao. Espera `dados_extraidos` + `minuta` + `engine_ia`."""
    return _invocar_webhook(
        webhook_url=get_n8n_peticao_webhook_url(),
        dados=dados,
        label="peticao",
        parse_response=_parse_estrito("contestacao-por-peticao"),
        vazio_fatal=True,
        mensagem_vazio="Workflow de contestacao-por-peticao retornou resposta vazia.",
    )


# ─────────────────────────── Wrappers assincronos ────────────────────────────


async def enviar_para_n8n(
    dados: dict[str, Any], webhook_url: str | None = None
) -> Any:
    """Envia payload sem bloquear o loop principal da API.

    `webhook_url` opcional sobrescreve a env var `N8N_WEBHOOK_URL` (PR8 P1.2).
    """
    return await asyncio.to_thread(_enviar_para_n8n_sync, dados, webhook_url)


async def enviar_para_n8n_edicao(dados: dict[str, Any]) -> Any:
    """Envia payload do fluxo de edicao sem bloquear o loop principal."""
    return await asyncio.to_thread(_enviar_para_n8n_edicao_sync, dados)


async def enviar_para_n8n_peticao(dados: dict[str, Any]) -> Any:
    """Envia payload do fluxo de contestacao-por-peticao sem bloquear o loop."""
    return await asyncio.to_thread(_enviar_para_n8n_peticao_sync, dados)
