"""Rotas POST /api/contestar-por-peticao + /api/contestacoes/{id}/confirmar-extracao.

Fluxo principal (`POST /contestar-por-peticao`):
1. Backend valida payload (Pydantic) e decodifica peticao + modelo + anexos.
2. Backend extrai e CONSOLIDA texto da peticao com texto dos anexos (PR5 multi-docs).
3. Envia texto consolidado + tipo_acao_hint + pontos_contestante para o n8n.
4. Workflow n8n: Claude Extrator -> RAG Supabase -> Claude Gerador.
5. **PR5 HiL**: se `dados_extraidos.confianca < CONFIANCA_THRESHOLD`, NAO gera DOCX,
   marca status `requer_revisao_humana` e retorna apenas dados extraidos para o
   advogado revisar antes de gerar a minuta.
6. Caso contrario, monta DOCX (docxtpl com modelo base ou programatico).
7. Backend persiste em `contestacoes` com origem='peticao'.
8. Retorna JSON com dados extraidos + minuta + DOCX em base64 (ou flag de revisao).

Fluxo de confirmacao (`POST /contestacoes/{id}/confirmar-extracao`):
1. Backend busca contestacao em DB e valida que pertence ao usuario e que esta
   em `requer_revisao_humana`.
2. Monta payload n8n com flag `dados_extraidos_pre_validados` (workflow detecta
   e BYPASSA o Claude Extrator, indo direto para RAG + Gerador).
3. Recebe minuta nova; monta DOCX; atualiza contestacao no DB.
4. Retorna shape igual ao happy path.

Nota: NAO usar `from __future__ import annotations` — quebra FastAPI/OpenAPI
quando combinado com Body(...).
"""

import base64
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status

from App.database import (
    atualizar_contestacao_pos_revisao,
    get_contestacao,
    salvar_minuta_editada,
    save_contestacao,
)
from App.limiter import limiter
from App.models.contestacao_por_peticao import (
    ConfirmacaoExtracao,
    ContestacaoPorPeticao,
    MinutaEditada,
)
from App.security import get_authenticated_user
from App.services.contestacao_docx_builder import (
    montar_docx_com_modelo,
    montar_docx_programatico,
)
from App.services.n8n_service import N8NServiceError, enviar_para_n8n_peticao
from App.services.diff_minuta import diff_secoes, resumo_diff
from App.services.peticao_extractor import (
    ExtracaoError,
    extrair_e_consolidar_textos,
    extrair_texto_modelo_base,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Limiar de confianca abaixo do qual a contestacao exige revisao humana antes
# de gerar o DOCX final (PR5 HiL — Guia Tecnico v3 secao 2.1).
CONFIANCA_THRESHOLD = 0.7


@router.post("/contestar-por-peticao")
@limiter.limit("10/minute")
async def contestar_por_peticao(
    request: Request,
    payload: ContestacaoPorPeticao = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Gera contestacao automaticamente a partir da peticao inicial enviada.

    Quando `dados_confianca >= 0.7` retorna a minuta + DOCX no fluxo normal.
    Quando `dados_confianca < 0.7` retorna `{requer_revisao_humana: True, ...}`
    e o frontend deve disparar o modal de revisao + chamar /confirmar-extracao.
    """

    # 1. Decodifica peticao
    try:
        peticao_bytes = base64.b64decode(payload.arquivo_peticao_base64)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conteudo da peticao invalido em base64.",
        ) from error

    # 2. Decodifica anexos (PR5 multi-docs) e consolida texto com a peticao.
    anexos_decodificados: list[tuple[bytes, str]] = []
    for anexo in payload.arquivos_anexos:
        try:
            anexos_decodificados.append((base64.b64decode(anexo.base64), anexo.nome))
        except Exception:
            logger.warning("Anexo descartado por base64 invalido: %s", anexo.nome)

    try:
        texto_peticao = extrair_e_consolidar_textos(
            peticao_bytes,
            payload.arquivo_peticao_nome,
            anexos_decodificados,
        )
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

    # 6. PR5 HiL: avalia confianca da extracao.
    confianca = _coerce_float(dados_extraidos.get("confianca"))
    requer_revisao = confianca is not None and confianca < CONFIANCA_THRESHOLD

    save_payload_base = {
        "usuario_id": usuario["id"],
        "numero_processo": dados_extraidos.get("numero_processo") or "a definir",
        "autor": dados_extraidos.get("autor") or "",
        "reu": dados_extraidos.get("reu") or "",
        "tipo_acao": dados_extraidos.get("tipo_acao") or payload.tipo_acao_hint or "Nao identificado",
        "fatos": dados_extraidos.get("fatos_resumo") or "",
        "pedido_autor": _join_pedidos(dados_extraidos.get("pedidos")),
        "arquivo_base_nome": payload.arquivo_peticao_nome,
        "arquivo_base_conteudo_base64": "",
        "arquivo_base_mime_type": payload.arquivo_peticao_mime_type,
        "arquivo_base_tamanho_bytes": len(peticao_bytes),
        "texto_editado_ao_vivo": "",
    }

    if requer_revisao:
        # Salva sem gerar DOCX. Frontend recebe dados extraidos para o
        # advogado revisar e enviar via /confirmar-extracao.
        try:
            contestacao_id = save_contestacao(
                payload=save_payload_base,
                status="requer_revisao_humana",
                n8n_resposta=resposta_n8n,
                origem="peticao",
                requer_revisao_humana=True,
                dados_confianca=confianca,
                minuta_json_original=minuta,
            )
        except Exception as error:
            logger.error(
                "Falha ao persistir contestacao em revisao usuario_id=%s erro=%s",
                usuario["id"],
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao persistir a contestacao gerada.",
            ) from error

        return {
            "status": "requer_revisao_humana",
            "contestacao_id": contestacao_id,
            "requer_revisao_humana": True,
            "dados_confianca": confianca,
            "dados_extraidos": dados_extraidos,
            "minuta_preview": minuta,
            "engine_ia": engine_ia,
            "mensagem": (
                f"A IA teve baixa confianca ({confianca:.2f}) na extracao dos "
                "dados. Revise os campos extraidos antes de gerar a minuta final."
            ),
        }

    # 7. Confianca alta: monta o .docx final
    docx_bytes = _montar_docx(payload, dados_extraidos, minuta, usuario["id"])

    # 8. Persiste com confianca + minuta original (golden dataset PR5)
    try:
        contestacao_id = save_contestacao(
            payload=save_payload_base,
            status=str(resposta_n8n.get("status") or "ok"),
            n8n_resposta=resposta_n8n,
            origem="peticao",
            requer_revisao_humana=False,
            dados_confianca=confianca,
            minuta_json_original=minuta,
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

    arquivo_editado_base64 = base64.b64encode(docx_bytes).decode("ascii")
    arquivo_editado_nome = _montar_nome_saida(dados_extraidos)

    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "requer_revisao_humana": False,
        "dados_confianca": confianca,
        "dados_extraidos": dados_extraidos,
        "minuta": minuta,
        "engine_ia": engine_ia,
        "arquivo_editado_base64": arquivo_editado_base64,
        "arquivo_editado_nome": arquivo_editado_nome,
        "arquivo_editado_mime_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    }


@router.post("/contestacoes/{contestacao_id}/confirmar-extracao")
@limiter.limit("10/minute")
async def confirmar_extracao(
    request: Request,
    contestacao_id: int = Path(..., gt=0),
    payload: ConfirmacaoExtracao = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Re-executa o pipeline com dados revisados pelo humano (PR5 HiL).

    O workflow n8n detecta `dados_extraidos_pre_validados` no payload e
    bypassa o Claude Extrator (poupando 1 chamada Claude e tokens). RAG +
    Gerador rodam normalmente com os dados corrigidos pelo advogado.
    """

    contestacao = get_contestacao(contestacao_id, usuario["id"])
    if contestacao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada para o usuario autenticado.",
        )

    if not contestacao.get("requer_revisao_humana"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta contestacao nao esta em revisao humana.",
        )

    dados_corrigidos = dict(payload.dados_extraidos)

    # Monta payload n8n com flag de bypass.
    payload_n8n = {
        # texto_peticao vazio: o extrator vai bypassar e usar dados_extraidos_pre_validados.
        "texto_peticao": "(revisao humana - extrator bypassado)",
        "modelo_base_texto": extrair_texto_modelo_base(payload.modelo_base_base64),
        "tipo_acao_hint": dados_corrigidos.get("tipo_acao", ""),
        "pontos_contestante": payload.pontos_contestante or "",
        "usuario_id": usuario["id"],
        "auth_provider": usuario.get("auth_provider", "legacy"),
        "dados_extraidos_pre_validados": dados_corrigidos,
    }

    try:
        resposta_n8n = await enviar_para_n8n_peticao(payload_n8n)
    except N8NServiceError as error:
        logger.error(
            "n8n confirmar-extracao indisponivel contestacao_id=%s erro=%s",
            contestacao_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de geracao indisponivel. Tente novamente em instantes.",
        ) from error

    if not isinstance(resposta_n8n, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de geracao.",
        )

    minuta_nova = resposta_n8n.get("minuta") or {}
    engine_ia = resposta_n8n.get("engine_ia") or {}

    if not minuta_nova:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de geracao nao retornou a minuta da contestacao.",
        )

    # Monta DOCX final com dados corrigidos pelo humano.
    docx_bytes = _montar_docx_minimal(payload, dados_corrigidos, minuta_nova, usuario["id"])

    arquivo_editado_base64 = base64.b64encode(docx_bytes).decode("ascii")
    arquivo_editado_nome = _montar_nome_saida(dados_corrigidos)

    # Atualiza contestacao no DB: status=ok, requer_revisao=false, nova minuta.
    atualizou = atualizar_contestacao_pos_revisao(
        contestacao_id=contestacao_id,
        usuario_id=usuario["id"],
        minuta_nova=minuta_nova,
        n8n_resposta_nova=resposta_n8n,
        dados_extraidos_corrigidos=dados_corrigidos,
    )
    if not atualizou:
        logger.error(
            "Falha ao atualizar contestacao pos-revisao id=%s usuario=%s",
            contestacao_id,
            usuario["id"],
        )

    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "requer_revisao_humana": False,
        "dados_extraidos": dados_corrigidos,
        "minuta": minuta_nova,
        "engine_ia": engine_ia,
        "arquivo_editado_base64": arquivo_editado_base64,
        "arquivo_editado_nome": arquivo_editado_nome,
        "arquivo_editado_mime_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    }


def _montar_docx(
    payload: ContestacaoPorPeticao,
    dados_extraidos: dict,
    minuta: dict,
    usuario_id: str,
) -> bytes:
    """Monta DOCX com modelo base (se houver) ou programatico. Levanta HTTPException em falha."""
    docx_bytes = None
    if payload.modelo_base_base64:
        docx_bytes = montar_docx_com_modelo(
            payload.modelo_base_base64, dados_extraidos, minuta
        )
    if docx_bytes is None:
        try:
            docx_bytes = montar_docx_programatico(dados_extraidos, minuta)
        except Exception as error:
            logger.error(
                "Falha ao montar .docx programatico usuario_id=%s erro=%s",
                usuario_id,
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao montar o arquivo da contestacao.",
            ) from error
    return docx_bytes


def _montar_docx_minimal(
    payload: ConfirmacaoExtracao,
    dados_extraidos: dict,
    minuta: dict,
    usuario_id: str,
) -> bytes:
    """Variante de _montar_docx para o fluxo de confirmacao (modelo base do payload)."""
    docx_bytes = None
    if payload.modelo_base_base64:
        docx_bytes = montar_docx_com_modelo(
            payload.modelo_base_base64, dados_extraidos, minuta
        )
    if docx_bytes is None:
        try:
            docx_bytes = montar_docx_programatico(dados_extraidos, minuta)
        except Exception as error:
            logger.error(
                "Falha ao montar .docx pos-revisao usuario_id=%s erro=%s",
                usuario_id,
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao montar o arquivo da contestacao.",
            ) from error
    return docx_bytes


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


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── PR5 Observabilidade: golden dataset (minuta original IA vs editada humano) ──


@router.patch("/contestacoes/{contestacao_id}/minuta")
@limiter.limit("30/minute")
async def atualizar_minuta_editada(
    request: Request,
    contestacao_id: int = Path(..., gt=0),
    payload: MinutaEditada = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Persiste edicao do advogado em `minuta_json_editada` (PR5 Observabilidade).

    A minuta original (gerada pela IA) fica intacta em `minuta_json_original`.
    O diff entre as duas e computado em tempo de leitura (futura rota de
    metricas / fine-tuning) ou pelo cliente que ler ambas.

    Frontend deve chamar com debounce (3s) durante edicao do liveDraft. Ate 5
    edicoes por minuto sao aceitas (rate limit 30/min cobre debounces normais).
    """
    contestacao = get_contestacao(contestacao_id, usuario["id"])
    if contestacao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada para o usuario autenticado.",
        )

    # Merge: parte da minuta_editada anterior (se houver) + campos enviados agora.
    minuta_anterior = contestacao.get("minuta_json_editada") or {}
    nova = dict(minuta_anterior)
    if payload.tese_central is not None:
        nova["tese_central"] = payload.tese_central
    if payload.preliminares is not None:
        nova["preliminares"] = payload.preliminares
    if payload.merito is not None:
        nova["merito"] = payload.merito
    if payload.fundamentos is not None:
        nova["fundamentos"] = payload.fundamentos
    if payload.pedidos is not None:
        nova["pedidos"] = payload.pedidos
    if payload.observacoes is not None:
        nova["observacoes"] = payload.observacoes
    if payload.impugnacao_pedidos is not None:
        nova["impugnacao_pedidos"] = payload.impugnacao_pedidos

    atualizou = salvar_minuta_editada(
        contestacao_id=contestacao_id,
        usuario_id=usuario["id"],
        minuta_editada=nova,
    )
    if not atualizou:
        # Race condition: contestacao foi removida entre o get e o update.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada para o usuario autenticado.",
        )

    # Calcula diff resumido (apenas para retornar ao frontend, nao persistido —
    # podemos recalcular sob demanda lendo as duas minutas).
    diff = diff_secoes(contestacao.get("minuta_json_original"), nova)

    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "diff_resumo": resumo_diff(diff),
    }
