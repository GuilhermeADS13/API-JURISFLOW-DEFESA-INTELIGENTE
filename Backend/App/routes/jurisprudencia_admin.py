"""Rotas admin de jurisprudencia_externa (PR22 + PR23).

PR22: POST /api/admin/jurisprudencia/criar — cadastro manual de paradigma.
PR23: GET /listar, GET /{id}, PATCH /{id}, DELETE /{id} — CRUD completo.

Auth: get_authenticated_user + _is_admin() (reusa helper de feedback.py).
Aceita usuario humano cujo email esta em ADMIN_EMAILS OU pseudo-user
backend_admin_token (chamadas internas n8n).

Idempotencia do POST: upsert da tabela faz match por
(tribunal, numero_processo) UNIQUE. Re-submissao do mesmo acordao atualiza
campos sem duplicar.

CRUD do PR23 trabalha por `id` (BIGSERIAL) — separado da chave de negocio.
"""

import logging
import threading

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, Field

from App.limiter import limiter
from App.models.jurisprudencia_manual import JurisprudenciaManual
from App.routes.feedback import _is_admin
from App.security import get_authenticated_user
from App.services.embedding_service import gerar_embedding

logger = logging.getLogger(__name__)
# PR27 (finding #8): dependencies aplicadas no router — cada endpoint recebe
# `usuario` ja validado via `exige_admin_dep`. Elimina risco de esquecer o
# guard manual em rota nova.
router = APIRouter()


def exige_admin_dep(
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict[str, str]:
    """FastAPI dependency: valida admin e retorna o usuario autenticado.

    PR27 (finding #8): substitui a antiga funcao `_exige_admin` que era
    chamada manualmente no topo de cada rota. Agora aplicada uma vez no
    APIRouter (dependencies=[Depends(exige_admin_dep)]) — evita risco de
    esquecer o guard num endpoint novo.
    """
    if not _is_admin(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores (ADMIN_EMAILS).",
        )
    return usuario


@router.post("/admin/jurisprudencia/criar", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def criar_jurisprudencia(
    request: Request,
    payload: JurisprudenciaManual,
    usuario: dict[str, str] = Depends(exige_admin_dep),
) -> dict:
    """Cadastra ou atualiza acordao paradigma em public.jurisprudencia_externa.

    Validacao Pydantic em `JurisprudenciaManual`:
      - tribunal, numero_processo, ementa obrigatorios + strip
      - peso_relevancia 1-10
      - data_julgamento opcional, mas se vier deve ser ISO 'YYYY-MM-DD'

    Embedding 384d local (sentence-transformers) gerado sobre
    `numero_processo + tese_firmada + ementa` — mesma estrategia do
    `scripts/ingest_seed_jurisprudencia.py` e do scraper STJ.

    Retorna 201 com {status, tribunal, numero_processo, embedding_gerado}.
    Falha de embedding NAO bloqueia o upsert (busca lexical continua
    funcionando mesmo sem vetor) — so loga warning.
    """
    # Import tardio: upsert_jurisprudencia toca o pool de conexoes do DB
    # so quando a rota e exercida. Evita inicializar pool no boot dos testes
    # que mockam tudo.
    from App.database import upsert_jurisprudencia

    texto_pra_embed = " ".join(
        filter(
            None,
            [
                payload.numero_processo,
                payload.tese_firmada or "",
                payload.ementa,
            ],
        )
    )
    embedding = gerar_embedding(texto_pra_embed)
    if embedding is None:
        logger.warning(
            "Cadastro manual sem embedding (provider local indisponivel?): %s %s",
            payload.tribunal,
            payload.numero_processo,
        )

    try:
        upsert_jurisprudencia(
            tribunal=payload.tribunal,
            numero_processo=payload.numero_processo,
            ementa=payload.ementa,
            tipo_decisao=payload.tipo_decisao,
            relator=payload.relator,
            data_julgamento=payload.data_julgamento,
            tese_firmada=payload.tese_firmada,
            area_juridica=payload.area_juridica,
            peso_relevancia=payload.peso_relevancia,
            fonte_url=payload.fonte_url,
            embedding=embedding,
            texto_integral=payload.texto_integral,
        )
    except Exception as err:
        logger.error(
            "Falha upsert jurisprudencia manual %s %s: %s",
            payload.tribunal,
            payload.numero_processo,
            err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao salvar no banco. Confira logs do backend.",
        ) from err

    logger.info(
        "Jurisprudencia paradigma cadastrada: %s %s por %s",
        payload.tribunal,
        payload.numero_processo,
        usuario.get("email", "?"),
    )

    return {
        "status": "ok",
        "tribunal": payload.tribunal,
        "numero_processo": payload.numero_processo,
        "peso_relevancia": payload.peso_relevancia,
        "embedding_gerado": embedding is not None,
        "mensagem": (
            f"{payload.tribunal} {payload.numero_processo} cadastrado/atualizado "
            f"em jurisprudencia_externa."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PR23 — CRUD (List, Get, Update, Delete)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/admin/jurisprudencia/listar")
@limiter.limit("60/minute")
async def listar(
    request: Request,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tribunal: str | None = Query(default=None, max_length=20),
    area_juridica: str | None = Query(default=None, max_length=40),
    busca: str | None = Query(
        default=None,
        max_length=200,
        description="ILIKE em numero_processo OU ementa OU relator",
    ),
    usuario: dict[str, str] = Depends(exige_admin_dep),
) -> dict:
    """Lista paginada de jurisprudencia (admin)."""
    from App.database import listar_jurisprudencia

    try:
        return listar_jurisprudencia(
            limit=limit,
            offset=offset,
            tribunal=tribunal,
            area_juridica=area_juridica,
            busca=busca,
        )
    except Exception as err:
        logger.error("Falha ao listar jurisprudencia: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar. Confira logs do backend.",
        ) from err


@router.get("/admin/jurisprudencia/{jurisprudencia_id}")
@limiter.limit("60/minute")
async def obter(
    request: Request,
    jurisprudencia_id: int,
    usuario: dict[str, str] = Depends(exige_admin_dep),
) -> dict:
    """Retorna 1 jurisprudencia por id, ou 404."""
    from App.database import obter_jurisprudencia

    item = obter_jurisprudencia(jurisprudencia_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Jurisprudencia id={jurisprudencia_id} nao encontrada.",
        )
    return item


@router.patch("/admin/jurisprudencia/{jurisprudencia_id}")
@limiter.limit("30/minute")
async def atualizar(
    request: Request,
    jurisprudencia_id: int,
    payload: JurisprudenciaManual,
    usuario: dict[str, str] = Depends(exige_admin_dep),
) -> dict:
    """Atualiza uma jurisprudencia. Payload completo (Pydantic) — recalcula embedding.

    PR27 (finding #6): elimina o `obter_jurisprudencia` previo. Antes: SELECT
    + gerar_embedding + UPDATE = 2 round-trips DB + custo de embedding
    mesmo quando registro nao existia. Agora: gera embedding + UPDATE com
    RETURNING id (atualizar_jurisprudencia retorna False se linha nao existe).
    Trade-off: embedding e gerado antes de saber se 404 — aceitavel porque
    embedding local custa ~50ms; DB round-trip poupado vale mais.
    """
    from App.database import atualizar_jurisprudencia

    texto_pra_embed = " ".join(
        filter(
            None,
            [
                payload.numero_processo,
                payload.tese_firmada or "",
                payload.ementa,
            ],
        )
    )
    embedding = gerar_embedding(texto_pra_embed)

    try:
        atualizou = atualizar_jurisprudencia(
            jurisprudencia_id,
            campos={
                "tribunal": payload.tribunal,
                "tipo_decisao": payload.tipo_decisao,
                "numero_processo": payload.numero_processo,
                "relator": payload.relator,
                "data_julgamento": payload.data_julgamento,
                "ementa": payload.ementa,
                "tese_firmada": payload.tese_firmada,
                "area_juridica": payload.area_juridica,
                "peso_relevancia": payload.peso_relevancia,
                "fonte_url": payload.fonte_url,
                "texto_integral": payload.texto_integral,
            },
            embedding=embedding,
        )
    except Exception as err:
        logger.error("Falha update jurisprudencia id=%s: %s", jurisprudencia_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar no banco. Confira logs do backend.",
        ) from err

    if not atualizou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Jurisprudencia id={jurisprudencia_id} nao encontrada.",
        )

    logger.info(
        "Jurisprudencia paradigma atualizada: id=%s %s %s por %s",
        jurisprudencia_id,
        payload.tribunal,
        payload.numero_processo,
        usuario.get("email", "?"),
    )
    return {
        "status": "ok",
        "id": jurisprudencia_id,
        "tribunal": payload.tribunal,
        "numero_processo": payload.numero_processo,
        "embedding_gerado": embedding is not None,
        "mensagem": (
            f"id={jurisprudencia_id} ({payload.tribunal} {payload.numero_processo}) atualizada."
        ),
    }


@router.delete(
    "/admin/jurisprudencia/{jurisprudencia_id}",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
async def deletar(
    request: Request,
    jurisprudencia_id: int,
    usuario: dict[str, str] = Depends(exige_admin_dep),
) -> dict:
    """Remove jurisprudencia por id. 404 se nao existia."""
    from App.database import deletar_jurisprudencia

    try:
        removeu = deletar_jurisprudencia(jurisprudencia_id)
    except Exception as err:
        logger.error("Falha delete jurisprudencia id=%s: %s", jurisprudencia_id, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover no banco. Confira logs do backend.",
        ) from err

    if not removeu:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Jurisprudencia id={jurisprudencia_id} nao encontrada.",
        )

    logger.info(
        "Jurisprudencia paradigma removida: id=%s por %s",
        jurisprudencia_id,
        usuario.get("email", "?"),
    )
    return {
        "status": "ok",
        "id": jurisprudencia_id,
        "mensagem": f"id={jurisprudencia_id} removida com sucesso.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PR34 — Ingestao em lote agendada (scraper TST/CARF via n8n Schedule Trigger)
# ─────────────────────────────────────────────────────────────────────────────


class ScrapeLoteRequest(BaseModel):
    """Corpo do POST /admin/jurisprudencia/scrape."""

    fonte: str = Field(
        default="tst", description="tst (trabalhista) | carf (tributario) | todas"
    )
    max_por_tema: int = Field(default=4, ge=1, le=20)


# Guard contra ingestoes concorrentes (schedule + disparo manual sobrepostos).
# O upsert e idempotente, entao concorrencia nao corrompe — so evita trabalho
# de embedding redundante. Non-blocking: se ja roda, pula.
_scrape_lock = threading.Lock()


def _rodar_scrape_background(fonte: str, max_por_tema: int) -> None:
    """Roda a ingestao em background. Excecoes ficam nos logs (nao ha response)."""
    from App.services.jurisprudencia_ingest import FONTES, ingerir_lote

    if not _scrape_lock.acquire(blocking=False):
        logger.warning("Scrape ja em andamento — ignorando disparo (fonte=%s).", fonte)
        return
    try:
        fontes = sorted(FONTES) if fonte == "todas" else [fonte]
        for f in fontes:
            try:
                stats = ingerir_lote(f, max_por_tema=max_por_tema)
                logger.info("Scrape agendado concluido: %s", stats)
            except Exception as err:  # noqa: BLE001 — background; so loga
                logger.error("Scrape agendado falhou fonte=%s: %s", f, err)
    finally:
        _scrape_lock.release()


@router.post("/admin/jurisprudencia/scrape", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("6/hour")
async def scrape_lote(
    request: Request,
    payload: ScrapeLoteRequest,
    background_tasks: BackgroundTasks,
    usuario: dict[str, str] = Depends(exige_admin_dep),
) -> dict:
    """Dispara ingestao em lote de jurisprudencia (assincrono).

    Alvo do Schedule Trigger do n8n pra crescer a base sem intervencao. Valida
    a fonte, agenda a coleta em background (dura ~50-80s por fonte) e retorna
    202 imediatamente — o n8n nao fica preso esperando. Stats vao pros logs.

    Fontes: `tst` (trabalhista), `carf` (tributario) ou `todas`.
    """
    from App.services.jurisprudencia_ingest import FONTES

    fonte = payload.fonte.lower().strip()
    validas = {*FONTES, "todas"}
    if fonte not in validas:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"fonte invalida: {fonte!r} (use {sorted(validas)}).",
        )

    background_tasks.add_task(_rodar_scrape_background, fonte, payload.max_por_tema)
    logger.info(
        "Scrape em lote agendado: fonte=%s max=%d por %s",
        fonte,
        payload.max_por_tema,
        usuario.get("email", "?"),
    )
    return {
        "status": "accepted",
        "fonte": fonte,
        "max_por_tema": payload.max_por_tema,
        "mensagem": "Ingestao iniciada em background. Veja stats nos logs do backend.",
    }
