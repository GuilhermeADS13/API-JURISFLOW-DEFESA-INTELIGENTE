"""Agente de edicao cirurgica — piloto da migracao n8n -> backend.

Faz o que o workflow n8n `editar-contestacao` fazia: um unico pedido ao
Claude que identifica, no texto do .docx, os pares antigo<->novo dos campos
pedidos. A saida estruturada (`output_config.format`) garante JSON valido pelo
schema, entao some o reparo de JSON do workflow. Devolve o MESMO shape da
resposta do n8n, e `routes/edicao.py` processa as duas engines do mesmo jeito.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# Mesmo default que o docker-compose da para CLAUDE_MODEL.
DEFAULT_MODEL = "claude-sonnet-5"
TIMEOUT_SECONDS = float(os.getenv("CLAUDE_EDICAO_TIMEOUT_SECONDS", "120"))

SYSTEM_PROMPT = """Voce e um agente de edicao cirurgica de documentos juridicos brasileiros.
Voce recebe o texto extraido de uma contestacao em .docx e ate 3 campos novos
(nome, numero_processo, valor_causa). Sua tarefa e identificar a OCORRENCIA
PRINCIPAL de cada campo no texto antigo e listar pares antigo<->novo.

REGRAS RIGOROSAS:
- Se um campo NOVO foi pedido mas NAO existe no texto, inclua-o em
  "campos_ausentes" e NAO crie substituicao para ele.
- "antigo" deve ser uma string EXATA do texto (case-sensitive, espacos
  exatos, sem reformatar).
- NAO invente ocorrencias. NAO faca outras alteracoes alem das pedidas.
- "ocorrencias_esperadas" e o numero EXATO de vezes que "antigo" aparece
  no texto. Conte com cuidado — o backend aborta se divergir.
- Para o campo "nome": identifique o nome da parte (Reclamado/Reu/Contestante).
  Use o nome COMPLETO como aparece ("Janaina Pereira da Silva Matos", nao
  apenas "Janaina").
- Para "numero_processo": identifique no formato CNJ
  (XXXXXXX-XX.XXXX.X.XX.XXXX). Capture o numero EXATO.
- Para "valor_causa": identifique valor monetario brasileiro (R$ X.XXX,XX)
  tipicamente apos rotulos como "valor da causa", "valor atribuido".
- Se houver MULTIPLAS ocorrencias do antigo, conte todas e liste apenas UMA
  entrada com o total em ocorrencias_esperadas (a substituicao e global)."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "substituicoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campo": {
                        "type": "string",
                        "enum": ["nome", "numero_processo", "valor_causa"],
                    },
                    "antigo": {"type": "string"},
                    "novo": {"type": "string"},
                    "ocorrencias_esperadas": {"type": "integer"},
                },
                "required": ["campo", "antigo", "novo", "ocorrencias_esperadas"],
                "additionalProperties": False,
            },
        },
        "campos_ausentes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["substituicoes", "campos_ausentes"],
    "additionalProperties": False,
}


def _resposta_erro(
    campos_novos: dict[str, str | None], motivo: str, modelo: str
) -> dict[str, Any]:
    """Mesmo shape do fallback do n8n: status='erro_ia' -> rota devolve 503."""
    return {
        "status": "erro_ia",
        "substituicoes": [],
        "campos_ausentes": [k for k, v in campos_novos.items() if v],
        "engine_ia": {
            "provider": "fallback_local",
            "model": modelo,
            "api_error": motivo,
        },
        "_debug": {"fallback_acionado": True, "fallback_motivo": motivo},
        "processado_em": datetime.now(timezone.utc).isoformat(),
    }


async def gerar_substituicoes(
    texto_documento: str, campos_novos: dict[str, str | None]
) -> dict[str, Any]:
    """Pede ao Claude os pares antigo<->novo. Nunca levanta: falha vira erro_ia."""
    modelo = os.getenv("CLAUDE_MODEL", "").strip() or DEFAULT_MODEL
    chave = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        return _resposta_erro(campos_novos, "ANTHROPIC_API_KEY nao configurada", modelo)

    # O SDK ja repete 429/5xx/erro de conexao com backoff (max_retries).
    client = anthropic.AsyncAnthropic(
        api_key=chave, timeout=TIMEOUT_SECONDS, max_retries=2
    )
    mensagem = (
        f"TEXTO_DOCUMENTO:\n{texto_documento}\n\n"
        f"CAMPOS_NOVOS:\n{json.dumps(campos_novos, ensure_ascii=False, indent=2)}"
    )
    try:
        resposta = await client.messages.create(
            model=modelo,
            max_tokens=16000,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": mensagem}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
    except anthropic.APIStatusError as error:
        logger.warning(
            "Agente de edicao: HTTP %s do Claude: %s", error.status_code, error.message
        )
        return _resposta_erro(campos_novos, f"http_{error.status_code}", modelo)
    except anthropic.APIConnectionError as error:
        logger.warning("Agente de edicao: falha de conexao com o Claude: %s", error)
        return _resposta_erro(campos_novos, "erro_conexao", modelo)

    if resposta.stop_reason in ("max_tokens", "refusal"):
        return _resposta_erro(
            campos_novos, f"stop_reason_{resposta.stop_reason}", modelo
        )

    texto = next((b.text for b in resposta.content if b.type == "text"), "")
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        return _resposta_erro(campos_novos, "resposta_nao_json", modelo)

    return {
        "status": "ok",
        "substituicoes": dados["substituicoes"],
        "campos_ausentes": dados["campos_ausentes"],
        "engine_ia": {
            "provider": "claude_backend",
            "model": modelo,
            "api_error": None,
            "tokens_input": resposta.usage.input_tokens,
            "tokens_output": resposta.usage.output_tokens,
        },
        "_debug": {"fallback_acionado": False, "fallback_motivo": None},
        "processado_em": datetime.now(timezone.utc).isoformat(),
    }
