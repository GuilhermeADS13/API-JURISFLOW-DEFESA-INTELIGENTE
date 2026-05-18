# Servico de integracao com webhook do n8n para disparo de workflows de contestacao.
import asyncio
import json
import logging
import os
import time
from typing import Any
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
        except (HTTPError, URLError, TimeoutError, OSError) as error:
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


class N8NServiceError(Exception):
    pass


def get_n8n_webhook_url() -> str:
    webhook_url = os.getenv("N8N_WEBHOOK_URL", DEFAULT_N8N_WEBHOOK_URL).strip()
    return webhook_url or DEFAULT_N8N_WEBHOOK_URL


def get_n8n_edicao_webhook_url() -> str:
    webhook_url = os.getenv(
        "N8N_EDICAO_WEBHOOK_URL", DEFAULT_N8N_EDICAO_WEBHOOK_URL
    ).strip()
    return webhook_url or DEFAULT_N8N_EDICAO_WEBHOOK_URL


def get_n8n_peticao_webhook_url() -> str:
    webhook_url = os.getenv(
        "N8N_WEBHOOK_PETICAO", DEFAULT_N8N_PETICAO_WEBHOOK_URL
    ).strip()
    return webhook_url or DEFAULT_N8N_PETICAO_WEBHOOK_URL


def get_n8n_webhook_auth_token() -> str:
    return os.getenv("N8N_WEBHOOK_AUTH_TOKEN", "").strip()


def _enviar_para_n8n_sync(dados: dict[str, Any]) -> Any:
    """Execucao sincrona do POST para n8n (usada em thread dedicada)."""
    webhook_url = get_n8n_webhook_url()
    body = json.dumps(dados).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    auth_token = get_n8n_webhook_auth_token()
    if auth_token:
        request_headers["Authorization"] = f"Bearer {auth_token}"

    request = Request(
        url=webhook_url,
        data=body,
        headers=request_headers,
        method="POST",
    )

    try:
        response_body = _enviar_com_retry(request, N8N_TIMEOUT_SECONDS, "contestacao")
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise N8NServiceError(
            f"Falha ao acionar o n8n em {webhook_url}. Verifique se o workflow esta ativo."
        ) from error

    if not response_body:
        logger.warning("n8n respondeu sem corpo em %s", webhook_url)
        return {"message": "Workflow acionado sem corpo de resposta."}

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

    # Valida e filtra campos desconhecidos para prevenir injecao de dados arbitrarios.
    if isinstance(raw, dict):
        from App.models.n8n_response import N8NResponse

        try:
            return N8NResponse(**raw).model_dump(exclude_none=True)
        except Exception:
            logger.warning(
                "Resposta n8n nao passou na validacao de schema — retornando status padrao"
            )
            return {"status": "processando"}

    return raw


async def enviar_para_n8n(dados: dict[str, Any]) -> Any:
    """Envia payload sem bloquear o loop principal da API."""
    return await asyncio.to_thread(_enviar_para_n8n_sync, dados)


def _enviar_para_n8n_edicao_sync(dados: dict[str, Any]) -> Any:
    """Execucao sincrona do POST para o webhook de edicao do n8n.

    Espera resposta JSON com `substituicoes` e `campos_ausentes` (formato
    `RespostaAgenteEdicao` em App.models.edicao). NAO valida o schema aqui:
    a rota chama `RespostaAgenteEdicao.model_validate(...)` para isolar a
    responsabilidade de validacao.
    """
    webhook_url = get_n8n_edicao_webhook_url()
    body = json.dumps(dados).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    auth_token = get_n8n_webhook_auth_token()
    if auth_token:
        request_headers["Authorization"] = f"Bearer {auth_token}"

    request = Request(
        url=webhook_url,
        data=body,
        headers=request_headers,
        method="POST",
    )

    try:
        response_body = _enviar_com_retry(request, N8N_TIMEOUT_SECONDS, "edicao")
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise N8NServiceError(
            f"Falha ao acionar o n8n em {webhook_url}. Verifique se o workflow esta ativo."
        ) from error

    if not response_body:
        logger.warning("n8n (edicao) respondeu sem corpo em %s", webhook_url)
        raise N8NServiceError("Workflow de edicao retornou resposta vazia.")

    try:
        return json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning(
            "n8n (edicao) retornou payload nao-JSON de %s: %s",
            webhook_url,
            type(error).__name__,
        )
        raise N8NServiceError(
            "Workflow de edicao retornou resposta nao-JSON."
        ) from error


async def enviar_para_n8n_edicao(dados: dict[str, Any]) -> Any:
    """Envia payload do fluxo de edicao sem bloquear o loop principal."""
    return await asyncio.to_thread(_enviar_para_n8n_edicao_sync, dados)


def _enviar_para_n8n_peticao_sync(dados: dict[str, Any]) -> Any:
    """POST sincrono para o webhook de contestacao-por-peticao do n8n.

    Espera resposta JSON com `dados_extraidos`, `minuta` e `engine_ia`. A
    montagem do DOCX final e do salvamento ficam por conta do backend.
    """
    webhook_url = get_n8n_peticao_webhook_url()
    body = json.dumps(dados).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    auth_token = get_n8n_webhook_auth_token()
    if auth_token:
        request_headers["Authorization"] = f"Bearer {auth_token}"

    request = Request(
        url=webhook_url,
        data=body,
        headers=request_headers,
        method="POST",
    )

    try:
        response_body = _enviar_com_retry(request, N8N_TIMEOUT_SECONDS, "peticao")
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise N8NServiceError(
            f"Falha ao acionar o n8n em {webhook_url}. Verifique se o workflow esta ativo."
        ) from error

    if not response_body:
        logger.warning("n8n (peticao) respondeu sem corpo em %s", webhook_url)
        raise N8NServiceError(
            "Workflow de contestacao-por-peticao retornou resposta vazia."
        )

    try:
        return json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning(
            "n8n (peticao) retornou payload nao-JSON de %s: %s",
            webhook_url,
            type(error).__name__,
        )
        raise N8NServiceError(
            "Workflow de contestacao-por-peticao retornou resposta nao-JSON."
        ) from error


async def enviar_para_n8n_peticao(dados: dict[str, Any]) -> Any:
    """Envia payload do fluxo de contestacao-por-peticao sem bloquear o loop."""
    return await asyncio.to_thread(_enviar_para_n8n_peticao_sync, dados)
