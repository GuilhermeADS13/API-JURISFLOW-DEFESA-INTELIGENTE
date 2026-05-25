"""Rota POST /api/editar-contestacao — edicao ciruurgica de .docx base.

Fluxo:
1. Backend valida o payload (Pydantic) e decodifica o .docx.
2. Backend extrai texto do .docx e envia para o n8n com os 3 campos novos.
3. Workflow n8n editar-contestacao chama Claude para identificar pares
   antigo<->novo e responde JSON com `substituicoes` e `campos_ausentes`.
4. Backend valida que cada `antigo` aparece exatamente `ocorrencias_esperadas`
   vezes no texto extraido (impede troca de ocorrencia errada).
5. Backend aplica substituicoes com python-docx, retorna .docx editado em
   base64 + relatorio textual.
"""

import base64
import binascii
import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import ValidationError

from App.limiter import limiter
from App.models.edicao import EdicaoContestacao, RespostaAgenteEdicao, SubstituicaoIA
from App.security import get_authenticated_user
from App.services.docx_editor import (
    SubstituicaoError,
    aplicar_substituicoes,
    extrair_texto,
)
from App.services.n8n_service import N8NServiceError, enviar_para_n8n_edicao

logger = logging.getLogger(__name__)

router = APIRouter()


def _montar_relatorio(
    substituicoes: list[SubstituicaoIA],
    campos_ausentes: list[str],
    payload: EdicaoContestacao,
) -> list[str]:
    """Constroi a lista de bullets do relatorio para o usuario.

    Formato espelha o que o ChatGPT entregou no caso de uso original:
    - "Nome antigo X substituido por Y."
    - "Numero do processo Z ajustado para W."
    - "Nao havia valor da causa especificado no documento; caso existisse
      teria sido atualizado para V."
    """
    rotulos = {
        "nome": "Nome",
        "numero_processo": "Numero do processo",
        "valor_causa": "Valor da causa",
    }
    valores_pedidos = {
        "nome": payload.nome_novo,
        "numero_processo": payload.numero_processo_novo,
        "valor_causa": payload.valor_causa_novo,
    }

    relatorio: list[str] = []
    for sub in substituicoes:
        rotulo = rotulos.get(sub.campo, sub.campo.capitalize())
        relatorio.append(
            f'{rotulo} antigo "{sub.antigo}" substituido por **{sub.novo}**.'
        )

    for campo in campos_ausentes:
        valor_pedido = valores_pedidos.get(campo)
        if not valor_pedido:
            continue
        rotulo = rotulos.get(campo, campo.capitalize())
        relatorio.append(
            f"Nao havia {rotulo.lower()} especificado no documento; "
            f"caso existisse teria sido atualizado para **{valor_pedido}**."
        )

    return relatorio


@router.post("/editar-contestacao")
@limiter.limit("5/minute")
async def editar_contestacao(
    request: Request,
    payload: EdicaoContestacao = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Recebe .docx base + campos novos, retorna .docx editado + relatorio."""
    docx_bytes = _decodificar_arquivo_base(payload.arquivo_base_conteudo_base64)
    texto_documento = _extrair_texto_seguro(docx_bytes, usuario["id"])

    payload_n8n = _montar_payload_n8n(payload, texto_documento, usuario)
    resposta_bruta, tempo_processamento_ms = await _chamar_workflow_edicao(
        payload_n8n, usuario["id"]
    )

    resposta = _processar_resposta_n8n(resposta_bruta, usuario["id"])
    _validar_substituicoes(resposta.substituicoes, texto_documento, usuario["id"])

    pares = [{"antigo": sub.antigo, "novo": sub.novo} for sub in resposta.substituicoes]
    docx_editado, ocorrencias = _aplicar_pares(pares, docx_bytes, usuario["id"])

    arquivo_editado_base64 = base64.b64encode(docx_editado).decode("ascii")
    arquivo_editado_nome = _montar_nome_saida(payload)
    relatorio = _montar_relatorio(
        resposta.substituicoes, resposta.campos_ausentes, payload
    )

    return {
        "status": "ok",
        "arquivo_editado_base64": arquivo_editado_base64,
        "arquivo_editado_nome": arquivo_editado_nome,
        "arquivo_editado_mime_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        "relatorio": relatorio,
        "campos_ausentes": resposta.campos_ausentes,
        "ocorrencias_aplicadas": ocorrencias,
        "tempo_processamento_ms": tempo_processamento_ms,
    }


def _decodificar_arquivo_base(b64: str) -> bytes:
    try:
        return base64.b64decode(b64)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conteudo do arquivo base invalido em base64.",
        ) from error


def _extrair_texto_seguro(docx_bytes: bytes, usuario_id: str) -> str:
    try:
        texto = extrair_texto(docx_bytes)
    except SubstituicaoError as error:
        logger.warning(
            "Falha ao extrair texto do .docx usuario_id=%s erro=%s",
            usuario_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nao foi possivel ler o arquivo .docx enviado.",
        ) from error

    if not texto.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O arquivo .docx nao contem texto extraivel.",
        )
    return texto


def _montar_payload_n8n(
    payload: EdicaoContestacao, texto: str, usuario: dict[str, str]
) -> dict:
    return {
        "texto_documento": texto,
        "campos_novos": {
            "nome": payload.nome_novo,
            "numero_processo": payload.numero_processo_novo,
            "valor_causa": payload.valor_causa_novo,
        },
        "usuario_id": usuario["id"],
        "auth_provider": usuario.get("auth_provider", "legacy"),
    }


async def _chamar_workflow_edicao(
    payload_n8n: dict, usuario_id: str
) -> tuple[object, int]:
    try:
        # PR8 P3.1 — mede tempo end-to-end da chamada ao n8n para observabilidade.
        t_inicio = time.monotonic()
        resposta_bruta = await enviar_para_n8n_edicao(payload_n8n)
        tempo_processamento_ms = int((time.monotonic() - t_inicio) * 1000)
    except N8NServiceError as error:
        # Mensagem generica ao cliente; detalhe completo no log do servico.
        logger.warning(
            "Workflow de edicao indisponivel usuario_id=%s erro=%s",
            usuario_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Servico de edicao temporariamente indisponivel. "
                "Tente novamente em instantes."
            ),
        ) from error
    return resposta_bruta, tempo_processamento_ms


def _processar_resposta_n8n(
    resposta_bruta: object, usuario_id: str
) -> RespostaAgenteEdicao:
    if not isinstance(resposta_bruta, dict):
        logger.warning(
            "Resposta inesperada do workflow de edicao tipo=%s",
            type(resposta_bruta).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de edicao.",
        )

    # PR9 P3.2 — workflow sinaliza falha da IA com status='erro_ia'.
    # Antes de validar schema, checar se foi fallback do n8n.
    if resposta_bruta.get("status") == "erro_ia":
        motivo = resposta_bruta.get("_debug", {}).get("fallback_motivo")
        logger.error(
            "n8n edicao retornou erro_ia usuario_id=%s motivo=%s",
            usuario_id,
            motivo,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servico de IA temporariamente indisponivel para edicao. Tente novamente em alguns minutos.",
        )

    try:
        return RespostaAgenteEdicao.model_validate(resposta_bruta)
    except ValidationError as error:
        logger.warning(
            "Resposta do workflow de edicao nao bate com schema: %s",
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de edicao.",
        ) from error


def _validar_substituicoes(
    substituicoes: list[SubstituicaoIA], texto: str, usuario_id: str
) -> None:
    """Cada `antigo` deve aparecer exatamente `ocorrencias_esperadas` vezes.

    Evita substituir a ocorrencia errada (ex: 'Joao' em 'Joao Silva' vs
    'Maria Joao').
    """
    divergencias = [
        {
            "campo": sub.campo,
            "antigo": sub.antigo,
            "ocorrencias_esperadas": sub.ocorrencias_esperadas,
            "ocorrencias_reais": texto.count(sub.antigo),
        }
        for sub in substituicoes
        if texto.count(sub.antigo) != sub.ocorrencias_esperadas
    ]
    if not divergencias:
        return

    logger.warning(
        "Divergencia de ocorrencias na edicao usuario_id=%s divergencias=%s",
        usuario_id,
        divergencias,
    )
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "O agente identificou substituicoes que nao batem com o "
            "documento. Revise o arquivo e tente novamente."
        ),
    )


def _aplicar_pares(
    pares: list[dict], docx_bytes: bytes, usuario_id: str
) -> tuple[bytes, dict]:
    if not pares:
        # Nao ha substituicoes (todos os campos pedidos estavam ausentes).
        # Devolve o arquivo original sem alteracao + relatorio explicativo.
        return docx_bytes, {}

    try:
        return aplicar_substituicoes(docx_bytes, pares)
    except SubstituicaoError as error:
        logger.error(
            "Falha ao aplicar substituicoes usuario_id=%s erro=%s",
            usuario_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao aplicar substituicoes no arquivo.",
        ) from error


def _montar_nome_saida(payload: EdicaoContestacao) -> str:
    """Constroi nome de arquivo da saida usando o numero novo se disponivel."""
    if payload.numero_processo_novo:
        sufixo = payload.numero_processo_novo.replace(".", "_").replace("-", "_")
        return f"contestacao_editada_{sufixo}.docx"
    return "contestacao_editada.docx"
