"""Rota POST /api/contestar-por-peticao — gera contestacao a partir da peticao inicial.

Fluxo:
1. Backend valida o payload (Pydantic) e decodifica peticao + modelo opcional.
2. Backend extrai texto da peticao (python-docx ou pypdf) e do modelo base.
3. Envia texto extraido + tipo_acao_hint + pontos_contestante para o n8n.
4. Workflow n8n contestar-por-peticao:
   - Claude extrai dados estruturados (autor, reu, pedidos, valores, ...)
   - RAG busca defesas anteriores no Supabase
   - Claude gera minuta JSON da contestacao
5. Backend monta o .docx final (docxtpl com modelo base, ou programatico).
6. Backend persiste em `contestacoes` com origem='peticao'.
7. Retorna JSON com dados extraidos + .docx em base64.

Nota: NAO usar `from __future__ import annotations` — quebra FastAPI/OpenAPI
quando combinado com Body(...).
"""

import base64
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from App.database import save_contestacao
from App.limiter import limiter
from App.models.contestacao_por_peticao import ContestacaoPorPeticao
from App.security import get_authenticated_user
from App.services.contestacao_docx_builder import (
    montar_docx_com_modelo,
    montar_docx_programatico,
)
from App.services.n8n_service import N8NServiceError, enviar_para_n8n_peticao
from App.services.peticao_extractor import (
    ExtracaoError,
    extrair_texto_modelo_base,
    extrair_texto_peticao,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/contestar-por-peticao")
@limiter.limit("10/minute")
async def contestar_por_peticao(
    request: Request,
    payload: ContestacaoPorPeticao = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Gera contestacao automaticamente a partir da peticao inicial enviada."""

    # 1. Decodifica peticao
    try:
        peticao_bytes = base64.b64decode(payload.arquivo_peticao_base64)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conteudo da peticao invalido em base64.",
        ) from error

    # 2. Extrai texto da peticao
    try:
        texto_peticao = extrair_texto_peticao(peticao_bytes, payload.arquivo_peticao_nome)
    except ExtracaoError as error:
        logger.warning(
            "Falha ao extrair texto da peticao usuario_id=%s erro=%s",
            usuario["id"],
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    # 3. Extrai texto do modelo base (opcional, nao falha)
    texto_modelo_base = extrair_texto_modelo_base(payload.modelo_base_base64)

    # 4. Monta payload para o n8n
    payload_n8n = {
        "texto_peticao": texto_peticao,
        "modelo_base_texto": texto_modelo_base,
        "tipo_acao_hint": payload.tipo_acao_hint or "",
        "pontos_contestante": payload.pontos_contestante or "",
        "usuario_id": usuario["id"],
        "auth_provider": usuario.get("auth_provider", "legacy"),
    }

    # 5. Chama o n8n
    try:
        resposta_n8n = await enviar_para_n8n_peticao(payload_n8n)
    except N8NServiceError as error:
        logger.error(
            "n8n contestar-por-peticao indisponivel usuario_id=%s erro=%s",
            usuario["id"],
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de geracao indisponivel. Tente novamente em instantes.",
        ) from error

    if not isinstance(resposta_n8n, dict):
        logger.warning(
            "Resposta inesperada do n8n contestar-por-peticao tipo=%s",
            type(resposta_n8n).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de geracao.",
        )

    dados_extraidos = resposta_n8n.get("dados_extraidos") or {}
    minuta = resposta_n8n.get("minuta") or {}
    engine_ia = resposta_n8n.get("engine_ia") or {}

    if not minuta:
        logger.warning(
            "n8n nao devolveu minuta usuario_id=%s status=%s",
            usuario["id"],
            resposta_n8n.get("status"),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de geracao nao retornou a minuta da contestacao.",
        )

    # 6. Monta o .docx final
    docx_bytes = None
    if payload.modelo_base_base64:
        docx_bytes = montar_docx_com_modelo(
            payload.modelo_base_base64, dados_extraidos, minuta
        )
    if docx_bytes is None:
        # Fallback ou modo sem modelo base.
        try:
            docx_bytes = montar_docx_programatico(dados_extraidos, minuta)
        except Exception as error:
            logger.error(
                "Falha ao montar .docx programatico usuario_id=%s erro=%s",
                usuario["id"],
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao montar o arquivo da contestacao.",
            ) from error

    arquivo_editado_base64 = base64.b64encode(docx_bytes).decode("ascii")
    arquivo_editado_nome = _montar_nome_saida(dados_extraidos)

    # 7. Persiste contestacao com origem='peticao'
    save_payload = {
        "usuario_id": usuario["id"],
        "numero_processo": dados_extraidos.get("numero_processo") or "a definir",
        "autor": dados_extraidos.get("autor") or "",
        "reu": dados_extraidos.get("reu") or "",
        "tipo_acao": dados_extraidos.get("tipo_acao") or payload.tipo_acao_hint or "Nao identificado",
        "fatos": dados_extraidos.get("fatos_resumo") or "",
        "pedido_autor": _join_pedidos(dados_extraidos.get("pedidos")),
        "arquivo_base_nome": payload.arquivo_peticao_nome,
        "arquivo_base_conteudo_base64": "",  # nao persistimos a peticao inteira
        "arquivo_base_mime_type": payload.arquivo_peticao_mime_type,
        "arquivo_base_tamanho_bytes": len(peticao_bytes),
        "texto_editado_ao_vivo": "",
    }

    try:
        contestacao_id = save_contestacao(
            payload=save_payload,
            status=str(resposta_n8n.get("status") or "ok"),
            n8n_resposta=resposta_n8n,
            origem="peticao",
        )
    except Exception as error:
        logger.error(
            "Falha ao persistir contestacao por peticao usuario_id=%s erro=%s",
            usuario["id"],
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao persistir a contestacao gerada.",
        ) from error

    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "dados_extraidos": dados_extraidos,
        "minuta": minuta,
        "engine_ia": engine_ia,
        "arquivo_editado_base64": arquivo_editado_base64,
        "arquivo_editado_nome": arquivo_editado_nome,
        "arquivo_editado_mime_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    }


def _montar_nome_saida(dados_extraidos: dict) -> str:
    numero = (dados_extraidos.get("numero_processo") or "").strip()
    if numero:
        sufixo = (
            "".join(c if c.isalnum() else "_" for c in numero)
            .strip("_")
        )
        return f"contestacao_{sufixo}.docx"
    return "contestacao.docx"


def _join_pedidos(pedidos) -> str:
    if isinstance(pedidos, list):
        return "; ".join(str(p) for p in pedidos if p)
    if pedidos is None:
        return ""
    return str(pedidos)
