"""Rotas POST /api/contestar-por-peticao + /api/contestacoes/{id}/confirmar-extracao.

Fluxo principal (`POST /contestar-por-peticao`):
1. Backend valida payload (Pydantic) e decodifica peticao + modelo + anexos.
2. Backend extrai e CONSOLIDA texto da peticao com texto dos anexos (PR5 multi-docs).
3. Envia texto consolidado + tipo_acao_hint + pontos_contestante para o n8n.
4. Workflow n8n: Claude Extrator -> RAG Supabase -> Claude Gerador.
5. **PR5 HiL**: se `dados_extraidos.confianca < CONFIANCA_THRESHOLD`, NAO gera DOCX,
   marca status `requer_revisao_humana` e retorna apenas dados extraidos para o
   advogado revisar antes de gerar a minuta.
6. Caso contrario, monta DOCX (python-docx com modelo base ou programatico).
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

Refatorado na Etapa 5: extrair_method para reduzir CC de `contestar_por_peticao`
(24 -> meta < 10) e `confirmar_extracao` (12 -> meta < 8), unificacao de
`_montar_docx`/`_montar_docx_minimal` e substituicao de broad `except Exception:`
por excecoes especificas com logging estruturado.
"""

import base64
import binascii
import logging
import threading

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status

from App.database import (
    atualizar_contestacao_pos_revisao,
    get_contestacao,
    get_contestacao_para_download,
    salvar_embedding,
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
from App.services.diff_minuta import diff_secoes, resumo_diff
from App.services.n8n_service import N8NServiceError, enviar_para_n8n_peticao
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

DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


# ─────────────────────────── Helpers de embedding ───────────────────────────


def _salvar_embedding_background(contestacao_id: int, texto: str) -> None:
    """Gera e persiste embedding em thread daemon (PR6 #4 RAG Semantico).

    Fire-and-forget: nao bloqueia a resposta da rota principal.
    Se a geracao falhar (chave ausente, erro API), apenas loga e ignora.
    """
    from App.services.embedding_service import gerar_embedding  # import lazy

    try:
        emb = gerar_embedding(texto)
        if emb:
            salvar_embedding(contestacao_id, emb)
    except Exception as err:  # noqa: BLE001 - background fire-and-forget: nao pode quebrar a thread
        logger.warning(
            "Falha ao salvar embedding contestacao_id=%s: %s",
            contestacao_id,
            err,
        )


def _disparar_embedding(contestacao_id: int, fatos: str, pedidos: str) -> None:
    """Lanca thread daemon para gerar embedding sem bloquear a resposta."""
    texto = f"{fatos} {pedidos}".strip()
    if not texto:
        return
    threading.Thread(
        target=_salvar_embedding_background,
        args=(contestacao_id, texto),
        daemon=True,
        name=f"embedding-{contestacao_id}",
    ).start()


# ─────────────────────── Helpers de decodificacao/extracao ────────────────────


def _decodificar_peticao_base64(peticao_b64: str) -> bytes:
    """Decodifica conteudo base64 da peticao ou levanta HTTP 422."""
    try:
        return base64.b64decode(peticao_b64)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conteudo da peticao invalido em base64.",
        ) from error


def _decodificar_anexos(anexos) -> list[tuple[bytes, str]]:
    """Decodifica anexos base64; anexos invalidos sao apenas logados e descartados."""
    decodificados: list[tuple[bytes, str]] = []
    for anexo in anexos:
        try:
            decodificados.append((base64.b64decode(anexo.base64), anexo.nome))
        except (binascii.Error, ValueError):
            logger.warning("Anexo descartado por base64 invalido: %s", anexo.nome)
    return decodificados


def _extrair_texto_peticao(
    peticao_bytes: bytes,
    nome: str,
    anexos: list[tuple[bytes, str]],
    usuario_id: str,
) -> str:
    """Wrapper do extrator que mapeia ExtracaoError para HTTP 422."""
    try:
        return extrair_e_consolidar_textos(peticao_bytes, nome, anexos)
    except ExtracaoError as error:
        logger.warning(
            "Falha ao extrair texto da peticao usuario_id=%s erro=%s",
            usuario_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


# ───────────────────────── Helpers de orquestracao n8n ────────────────────────


async def _chamar_n8n_peticao(
    payload_n8n: dict,
    *,
    fluxo: str,
    contexto_log: str,
) -> tuple[dict, dict]:
    """Chama o webhook n8n de peticao e devolve (resposta_n8n, minuta).

    Mapeia falhas conhecidas para HTTP 502 com mensagem amigavel.
    `fluxo` e `contexto_log` aparecem nos logs para distinguir os dois fluxos
    (contestar inicial vs confirmar pos-revisao humana).
    """
    try:
        resposta = await enviar_para_n8n_peticao(payload_n8n)
    except N8NServiceError as error:
        logger.error(
            "n8n %s indisponivel %s erro=%s", fluxo, contexto_log, error
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de geracao indisponivel. Tente novamente em instantes.",
        ) from error

    if not isinstance(resposta, dict):
        logger.warning(
            "Resposta inesperada do n8n %s tipo=%s", fluxo, type(resposta).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do servico de geracao.",
        )

    # Workflow sinaliza falha da IA (fallback acionado) com status='erro_ia'.
    # Sem este guard o backend monta DOCX com o conteudo do fallback e entrega
    # ao usuario uma peca quebrada (sem preliminares, com texto generico).
    if resposta.get("status") == "erro_ia":
        engine = resposta.get("engine_ia") or {}
        api_error = engine.get("api_error") or "erro desconhecido"
        logger.error(
            "n8n %s caiu em fallback %s api_error=%s provider=%s",
            fluxo,
            contexto_log,
            api_error,
            engine.get("provider"),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Falha no gerador de IA (a chamada externa foi abortada). "
                "Tente novamente em alguns segundos — em peticoes longas, "
                "o gerador as vezes precisa de uma segunda tentativa."
            ),
        )

    minuta = resposta.get("minuta") or {}
    if not minuta:
        logger.warning(
            "n8n %s nao devolveu minuta %s status=%s",
            fluxo,
            contexto_log,
            resposta.get("status"),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Servico de geracao nao retornou a minuta da contestacao.",
        )

    return resposta, minuta


# ────────────────────────── Helpers de persistencia ──────────────────────────


def _montar_save_payload(
    payload: ContestacaoPorPeticao,
    dados_extraidos: dict,
    usuario_id: str,
    peticao_bytes: bytes,
) -> dict:
    """Monta dict base usado tanto no fluxo OK quanto no requer_revisao_humana."""
    return {
        "usuario_id": usuario_id,
        "numero_processo": dados_extraidos.get("numero_processo") or "a definir",
        "autor": dados_extraidos.get("autor") or "",
        "reu": dados_extraidos.get("reu") or "",
        "tipo_acao": (
            dados_extraidos.get("tipo_acao")
            or payload.tipo_acao_hint
            or "Nao identificado"
        ),
        "fatos": dados_extraidos.get("fatos_resumo") or "",
        "pedido_autor": _join_pedidos(dados_extraidos.get("pedidos")),
        "arquivo_base_nome": payload.arquivo_peticao_nome,
        "arquivo_base_conteudo_base64": "",
        "arquivo_base_mime_type": payload.arquivo_peticao_mime_type,
        "arquivo_base_tamanho_bytes": len(peticao_bytes),
        "texto_editado_ao_vivo": "",
        # Persiste o modelo do escritorio pra regenerar o DOCX depois
        "modelo_base_b64": payload.modelo_base_base64 or "",
        "modelo_base_nome": payload.modelo_base_nome or "",
    }


def _persistir_contestacao(usuario_id: str, contexto: str, **kwargs) -> int:
    """Wrapper de save_contestacao que mapeia falhas para HTTP 500."""
    try:
        return save_contestacao(**kwargs)
    except (RuntimeError, ValueError, OSError) as error:
        logger.error(
            "Falha ao persistir contestacao %s usuario_id=%s erro=%s",
            contexto,
            usuario_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao persistir a contestacao gerada.",
        ) from error


# ───────────────────────── Helpers de montagem do DOCX ────────────────────────


def _montar_docx(
    modelo_b64: str | None,
    *,
    dados_extraidos: dict,
    minuta: dict,
    usuario_id: str,
    contexto: str = "",
) -> bytes:
    """Monta DOCX com modelo base (se houver) ou cai no programatico.

    Unifica o que antes eram `_montar_docx` e `_montar_docx_minimal`, eliminando
    duplicacao: ambos chamavam `montar_docx_com_modelo` + fallback identico.
    """
    docx_bytes = None
    if modelo_b64:
        docx_bytes = montar_docx_com_modelo(modelo_b64, dados_extraidos, minuta)
    if docx_bytes is not None:
        return docx_bytes

    try:
        return montar_docx_programatico(dados_extraidos, minuta)
    except (RuntimeError, ValueError, OSError) as error:
        logger.error(
            "Falha ao montar .docx programatico %s usuario_id=%s erro=%s",
            contexto,
            usuario_id,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao montar o arquivo da contestacao.",
        ) from error


def _resposta_docx(docx_bytes: bytes, dados_extraidos: dict) -> dict:
    """Encapsula encoding base64 + nome + mime do DOCX para resposta JSON."""
    return {
        "arquivo_editado_base64": base64.b64encode(docx_bytes).decode("ascii"),
        "arquivo_editado_nome": _montar_nome_saida(dados_extraidos),
        "arquivo_editado_mime_type": DOCX_MIME_TYPE,
    }


# ─────────────────────────────── Rotas ───────────────────────────────────────


# Cada call custa ~US$0.24 e usa 5 min do task runner do n8n. Para limitar
# cost amplification e DoS por usuario autenticado, estreitamos a janela
# minuto e adicionamos teto horario. Pilha: a regra mais restritiva ganha.
@router.post("/contestar-por-peticao")
@limiter.limit("30/hour")
@limiter.limit("5/minute")
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
    usuario_id = usuario["id"]

    # 1-2. Decodifica peticao + anexos e consolida o texto.
    peticao_bytes = _decodificar_peticao_base64(payload.arquivo_peticao_base64)
    anexos = _decodificar_anexos(payload.arquivos_anexos)
    texto_peticao = _extrair_texto_peticao(
        peticao_bytes, payload.arquivo_peticao_nome, anexos, usuario_id
    )

    # 3-4. Texto do modelo base e payload para o n8n.
    texto_modelo_base = extrair_texto_modelo_base(payload.modelo_base_base64)
    payload_n8n = {
        "texto_peticao": texto_peticao,
        "modelo_base_texto": texto_modelo_base,
        "tipo_acao_hint": payload.tipo_acao_hint or "",
        "pontos_contestante": payload.pontos_contestante or "",
        "usuario_id": usuario_id,
        "auth_provider": usuario.get("auth_provider", "legacy"),
    }

    # 5. Chamada ao n8n (com validacao e mapeamento de erros).
    resposta_n8n, minuta = await _chamar_n8n_peticao(
        payload_n8n,
        fluxo="contestar-por-peticao",
        contexto_log=f"usuario_id={usuario_id}",
    )

    dados_extraidos = resposta_n8n.get("dados_extraidos") or {}
    engine_ia = resposta_n8n.get("engine_ia") or {}
    confianca = _coerce_float(dados_extraidos.get("confianca"))
    save_payload_base = _montar_save_payload(
        payload, dados_extraidos, usuario_id, peticao_bytes
    )

    # 6. PR5 HiL: confianca baixa -> nao gera DOCX, retorna para revisao.
    if confianca is not None and confianca < CONFIANCA_THRESHOLD:
        return _fluxo_revisao_humana(
            usuario_id=usuario_id,
            save_payload_base=save_payload_base,
            resposta_n8n=resposta_n8n,
            minuta=minuta,
            dados_extraidos=dados_extraidos,
            engine_ia=engine_ia,
            confianca=confianca,
        )

    # 7-8. Confianca alta: monta DOCX, persiste e retorna minuta final.
    return _fluxo_ok(
        payload=payload,
        usuario_id=usuario_id,
        save_payload_base=save_payload_base,
        resposta_n8n=resposta_n8n,
        minuta=minuta,
        dados_extraidos=dados_extraidos,
        engine_ia=engine_ia,
        confianca=confianca,
    )


def _fluxo_revisao_humana(
    *,
    usuario_id: str,
    save_payload_base: dict,
    resposta_n8n: dict,
    minuta: dict,
    dados_extraidos: dict,
    engine_ia: dict,
    confianca: float,
) -> dict:
    """Salva contestacao em estado requer_revisao_humana e devolve preview."""
    contestacao_id = _persistir_contestacao(
        usuario_id,
        contexto="em revisao",
        payload=save_payload_base,
        status="requer_revisao_humana",
        n8n_resposta=resposta_n8n,
        origem="peticao",
        requer_revisao_humana=True,
        dados_confianca=confianca,
        minuta_json_original=minuta,
    )
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


def _fluxo_ok(
    *,
    payload: ContestacaoPorPeticao,
    usuario_id: str,
    save_payload_base: dict,
    resposta_n8n: dict,
    minuta: dict,
    dados_extraidos: dict,
    engine_ia: dict,
    confianca: float | None,
) -> dict:
    """Monta DOCX, persiste e devolve resposta de minuta pronta."""
    docx_bytes = _montar_docx(
        payload.modelo_base_base64,
        dados_extraidos=dados_extraidos,
        minuta=minuta,
        usuario_id=usuario_id,
    )

    contestacao_id = _persistir_contestacao(
        usuario_id,
        contexto="por peticao",
        payload=save_payload_base,
        status=str(resposta_n8n.get("status") or "ok"),
        n8n_resposta=resposta_n8n,
        origem="peticao",
        requer_revisao_humana=False,
        dados_confianca=confianca,
        minuta_json_original=minuta,
    )

    # PR6 #4: embedding em background (nao bloqueia resposta)
    _disparar_embedding(
        contestacao_id,
        save_payload_base.get("fatos", ""),
        save_payload_base.get("pedido_autor", ""),
    )

    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "requer_revisao_humana": False,
        "dados_confianca": confianca,
        "dados_extraidos": dados_extraidos,
        "minuta": minuta,
        "engine_ia": engine_ia,
        **_resposta_docx(docx_bytes, dados_extraidos),
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
    usuario_id = usuario["id"]
    contestacao = _carregar_contestacao_em_revisao(contestacao_id, usuario_id)

    dados_corrigidos = dict(payload.dados_extraidos)
    payload_n8n = _montar_payload_revisao(payload, dados_corrigidos, usuario)

    resposta_n8n, minuta_nova = await _chamar_n8n_peticao(
        payload_n8n,
        fluxo="confirmar-extracao",
        contexto_log=f"contestacao_id={contestacao_id}",
    )
    engine_ia = resposta_n8n.get("engine_ia") or {}

    docx_bytes = _montar_docx(
        payload.modelo_base_base64,
        dados_extraidos=dados_corrigidos,
        minuta=minuta_nova,
        usuario_id=usuario_id,
        contexto="pos-revisao",
    )

    if not atualizar_contestacao_pos_revisao(
        contestacao_id=contestacao_id,
        usuario_id=usuario_id,
        minuta_nova=minuta_nova,
        n8n_resposta_nova=resposta_n8n,
        dados_extraidos_corrigidos=dados_corrigidos,
    ):
        logger.error(
            "Falha ao atualizar contestacao pos-revisao id=%s usuario=%s",
            contestacao_id,
            usuario_id,
        )

    # PR6 #4: re-gera embedding com dados corrigidos pelo humano
    _disparar_embedding(
        contestacao_id,
        str(dados_corrigidos.get("fatos_resumo") or ""),
        str(dados_corrigidos.get("pedido_autor") or ""),
    )
    # Sem warning: contestacao foi carregada em _carregar_contestacao_em_revisao.
    _ = contestacao

    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "requer_revisao_humana": False,
        "dados_extraidos": dados_corrigidos,
        "minuta": minuta_nova,
        "engine_ia": engine_ia,
        **_resposta_docx(docx_bytes, dados_corrigidos),
    }


def _carregar_contestacao_em_revisao(contestacao_id: int, usuario_id: str) -> dict:
    """Recupera contestacao do DB e valida que esta em revisao humana."""
    contestacao = get_contestacao(contestacao_id, usuario_id)
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
    return contestacao


@router.get("/contestacoes/{contestacao_id}/baixar")
@limiter.limit("30/minute")
async def baixar_contestacao(
    request: Request,
    contestacao_id: int = Path(..., gt=0),
    formato: str = Query("docx", pattern="^(docx|pdf)$"),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Regenera o DOCX de uma contestacao a partir do banco e retorna em base64.

    Usado quando o frontend perde a resposta inicial (timeout/abort) mas a
    peca foi salva com sucesso. Reconstroi o .docx on-the-fly a partir do
    `n8n_resposta` (com `dados_extraidos` + `minuta`) e do `arquivo_base`
    (modelo do escritorio, opcional).
    """
    usuario_id = usuario["id"]
    contestacao = get_contestacao_para_download(contestacao_id, usuario_id)
    if contestacao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada ou nao pertence ao usuario.",
        )
    if contestacao["status"] != "ok":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Contestacao em status '{contestacao['status']}' — nao ha peca"
                " pronta para baixar."
            ),
        )

    n8n_resp = contestacao["n8n_resposta"] or {}
    dados_extraidos = n8n_resp.get("dados_extraidos") or {}
    # Se o usuario editou a minuta, prioriza a versao editada
    minuta = contestacao.get("minuta_json_editada") or n8n_resp.get("minuta") or {}
    if not minuta:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Minuta vazia — nada para renderizar.",
        )

    # Fallback de dados_extraidos a partir das colunas raiz, caso o JSON
    # esteja parcial (preserva ID do processo / partes pelo menos).
    for campo in ("numero_processo", "autor", "reu", "tipo_acao"):
        dados_extraidos.setdefault(campo, contestacao[campo])

    docx_bytes = _montar_docx(
        modelo_b64=contestacao.get("modelo_base_b64") or None,
        dados_extraidos=dados_extraidos,
        minuta=minuta,
        usuario_id=usuario_id,
        contexto=f"download contestacao_id={contestacao_id}",
    )

    if formato == "pdf":
        from App.services.pdf_converter import PdfConversionError, docx_to_pdf

        try:
            pdf_bytes = docx_to_pdf(docx_bytes)
        except PdfConversionError as exc:
            logger.error(
                "Falha conversao DOCX->PDF contestacao_id=%s erro=%s",
                contestacao_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Conversao para PDF indisponivel. Baixe em DOCX e converta no Word."
                ),
            ) from exc

        nome_docx = _montar_nome_saida(dados_extraidos)
        nome_pdf = nome_docx[:-5] + ".pdf" if nome_docx.endswith(".docx") else nome_docx + ".pdf"
        return {
            "arquivo_editado_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "arquivo_editado_nome": nome_pdf,
            "arquivo_editado_mime_type": "application/pdf",
        }

    return _resposta_docx(docx_bytes, dados_extraidos)


@router.delete("/contestacoes/{contestacao_id}")
@limiter.limit("20/minute")
async def excluir_contestacao_rota(
    request: Request,
    contestacao_id: int = Path(..., gt=0),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Deleta contestacao do usuario autenticado. IDOR-safe via filtro usuario_id."""
    from App.database import excluir_contestacao

    sucesso = excluir_contestacao(contestacao_id, usuario["id"])
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada ou nao pertence ao usuario.",
        )
    logger.info(
        "Contestacao excluida id=%s usuario_id=%s", contestacao_id, usuario["id"]
    )
    return {"status": "deleted", "contestacao_id": contestacao_id}


def _montar_payload_revisao(
    payload: ConfirmacaoExtracao,
    dados_corrigidos: dict,
    usuario: dict[str, str],
) -> dict:
    """Monta payload n8n com flag de bypass do Claude Extrator."""
    return {
        # Extrator vai bypassar e usar dados_extraidos_pre_validados.
        "texto_peticao": "(revisao humana - extrator bypassado)",
        "modelo_base_texto": extrair_texto_modelo_base(payload.modelo_base_base64),
        "tipo_acao_hint": dados_corrigidos.get("tipo_acao", ""),
        "pontos_contestante": payload.pontos_contestante or "",
        "usuario_id": usuario["id"],
        "auth_provider": usuario.get("auth_provider", "legacy"),
        "dados_extraidos_pre_validados": dados_corrigidos,
    }


# ──────────────────────────────── Utilitarios ────────────────────────────────


def _montar_nome_saida(dados_extraidos: dict) -> str:
    numero = (dados_extraidos.get("numero_processo") or "").strip()
    if numero:
        sufixo = "".join(c if c.isalnum() else "_" for c in numero).strip("_")
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

    nova = _aplicar_patches_minuta(
        minuta_anterior=contestacao.get("minuta_json_editada") or {},
        patch=payload,
    )

    if not salvar_minuta_editada(
        contestacao_id=contestacao_id,
        usuario_id=usuario["id"],
        minuta_editada=nova,
    ):
        # Race condition: contestacao foi removida entre o get e o update.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestacao nao encontrada para o usuario autenticado.",
        )

    diff = diff_secoes(contestacao.get("minuta_json_original"), nova)
    return {
        "status": "ok",
        "contestacao_id": contestacao_id,
        "diff_resumo": resumo_diff(diff),
    }


# Campos da MinutaEditada que sao aplicados em ordem como patch parcial.
# Manter sincronizado com o modelo `MinutaEditada`.
_CAMPOS_MINUTA_EDITAVEL = (
    "tese_central",
    "preliminares",
    "merito",
    "fundamentos",
    "pedidos",
    "observacoes",
    "impugnacao_pedidos",
)


def _aplicar_patches_minuta(*, minuta_anterior: dict, patch: MinutaEditada) -> dict:
    """Aplica campos nao-None de `patch` sobre `minuta_anterior` (merge parcial)."""
    nova = dict(minuta_anterior)
    for campo in _CAMPOS_MINUTA_EDITAVEL:
        valor = getattr(patch, campo, None)
        if valor is not None:
            nova[campo] = valor
    return nova
