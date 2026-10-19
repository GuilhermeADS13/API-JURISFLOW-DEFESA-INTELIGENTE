"""Rota POST /api/jurisprudencia/buscar — busca hibrida em public.jurisprudencia_externa.

PR19 — Fase 1. Consumida pelo workflow contestar-por-peticao (novo node 'Buscar
Jurisprudencia Aplicavel' entre 'Buscar Legislacao Aplicavel' e 'Claude Gerador').
Retorna acordaos verbatim pra serem injetados no SYSTEM_GERACAO, eliminando
alucinacao de citacoes processuais (ex: REsp 1.234.567/SP que nao existe).

Desenho identico ao /api/legislacao/buscar:
- semantica via pgvector (embedding query 384d)
- lexical via ts_rank_cd + plainto_tsquery('portuguese')
- mescla via Reciprocal Rank Fusion (k=60)

Diferencas:
- Cap em 3 (acordaos tem ementa longa; queremos few-shot, nao flood)
- Filtro temporal default 2018-01-01 (jurisprudencia antiga pode estar superada)
- Rerank pondera peso_relevancia (Sumula Vinculante=10 > Acordao comum=5)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Request

from App.database import (
    JURISPRUDENCIA_DATA_MINIMA_DEFAULT,
    buscar_jurisprudencia_lexical,
    buscar_jurisprudencia_semantica,
)
from App.limiter import limiter
from App.security import get_authenticated_user
from App.services.embedding_service import gerar_embedding_query

logger = logging.getLogger(__name__)
router = APIRouter()

_RRF_K = 60
_CANDIDATOS_POR_BUSCA = 6
_TOP_N_FINAL = 3  # acordaos > legislacao: ementa longa, manter few-shot


def _resposta_vazia(status_code: str, detalhe: str) -> dict:
    return {"status": status_code, "detalhe": detalhe, "acordaos": [], "total": 0}


def _normalizar_input(payload: dict) -> tuple[str, str | None, str]:
    """Extrai (texto_query, area_juridica, data_minima) do payload."""
    fatos = str(payload.get("fatos") or "").strip()
    pedidos_raw = payload.get("pedidos") or []
    pedidos_str = (
        " ".join(str(p) for p in pedidos_raw)
        if isinstance(pedidos_raw, list)
        else str(pedidos_raw)
    )
    tese = str(payload.get("tese_central") or "").strip()
    texto_query = f"{fatos} {pedidos_str} {tese}".strip()
    area_raw = payload.get("area_juridica")
    area_juridica = str(area_raw).strip().lower() if area_raw else None
    data_minima = str(payload.get("data_minima") or JURISPRUDENCIA_DATA_MINIMA_DEFAULT)
    return texto_query, area_juridica, data_minima


def _executar_semantica(
    embedding: list[float] | None,
    area_juridica: str | None,
    data_minima: str,
) -> list[dict]:
    if embedding is None:
        return []
    try:
        return buscar_jurisprudencia_semantica(
            embedding=embedding,
            area_juridica=area_juridica,
            limit=_CANDIDATOS_POR_BUSCA,
            data_minima=data_minima,
        )
    except Exception as err:
        logger.error(
            "Falha na busca semantica de jurisprudencia area=%s erro=%s",
            area_juridica,
            err,
        )
        return []


def _executar_lexical(
    texto_query: str,
    area_juridica: str | None,
    data_minima: str,
) -> list[dict]:
    try:
        return buscar_jurisprudencia_lexical(
            texto_query=texto_query,
            area_juridica=area_juridica,
            limit=_CANDIDATOS_POR_BUSCA,
            data_minima=data_minima,
        )
    except Exception as err:
        logger.error(
            "Falha na busca lexical de jurisprudencia area=%s erro=%s",
            area_juridica,
            err,
        )
        return []


def _mesclar_rrf(semanticos: list[dict], lexicais: list[dict]) -> list[dict]:
    """RRF sobre (tribunal, numero_processo) — chave UNIQUE da tabela."""
    rrf_scores: dict[tuple[str, str], float] = {}
    acordaos_por_chave: dict[tuple[str, str], dict] = {}

    for idx, ac in enumerate(semanticos, start=1):
        chave = (ac.get("tribunal", ""), ac.get("numero_processo", ""))
        rrf_scores[chave] = rrf_scores.get(chave, 0.0) + 1.0 / (_RRF_K + idx)
        acordaos_por_chave.setdefault(chave, ac)

    for idx, ac in enumerate(lexicais, start=1):
        chave = (ac.get("tribunal", ""), ac.get("numero_processo", ""))
        rrf_scores[chave] = rrf_scores.get(chave, 0.0) + 1.0 / (_RRF_K + idx)
        acordaos_por_chave.setdefault(chave, ac)

    resultado = []
    for chave, score in rrf_scores.items():
        ac = dict(acordaos_por_chave[chave])
        ac["rrf_score"] = score * (_RRF_K + 1)
        resultado.append(ac)
    resultado.sort(key=lambda a: a["rrf_score"], reverse=True)
    return resultado[:_TOP_N_FINAL]


@router.post("/jurisprudencia/buscar")
@limiter.limit("60/minute")
async def buscar_jurisprudencia(
    request: Request,
    payload: dict = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Busca acordaos relevantes via hibrida (vetorial + lexical + RRF).

    Payload:
        fatos: str           — resumo dos fatos extraidos (opcional)
        pedidos: list|str    — pedidos do autor
        tese_central: str    — tese gerada pelo RAG anterior (opcional, refina query)
        area_juridica: str   — filtro opcional (trabalhista|consumidor|...)
        data_minima: str     — ISO YYYY-MM-DD; default 2018-01-01

    Retorna top 3 acordaos com {tribunal, tipo_decisao, numero_processo, relator,
    data_julgamento, ementa, tese_firmada, area_juridica, peso_relevancia,
    fonte_url, score} pra serem injetados verbatim no prompt do Gerador.
    """
    texto_query, area_juridica, data_minima = _normalizar_input(payload)

    if not texto_query:
        return _resposta_vazia(
            "sem_texto", "fatos, pedidos e tese vazios — nao e possivel buscar"
        )

    embedding = gerar_embedding_query(texto_query)
    if embedding is None:
        logger.info("Busca jurisprudencia sem embedding — caindo em lexical-only")

    semanticos = _executar_semantica(embedding, area_juridica, data_minima)
    lexicais = _executar_lexical(texto_query, area_juridica, data_minima)

    if not semanticos and not lexicais:
        return _resposta_vazia(
            "sem_resultados",
            "Nenhuma jurisprudencia indexada bate com esta query. "
            "Rode `python scripts/scrape_jurisprudencia.py` pra popular a base.",
        )

    mesclados = _mesclar_rrf(semanticos, lexicais)
    acordaos = [
        {
            "tribunal": a["tribunal"],
            "tipo_decisao": a["tipo_decisao"],
            "numero_processo": a["numero_processo"],
            "relator": a.get("relator"),
            "data_julgamento": a.get("data_julgamento"),
            "ementa": a["ementa"],
            "tese_firmada": a.get("tese_firmada"),
            "area_juridica": a.get("area_juridica"),
            "peso_relevancia": a.get("peso_relevancia", 5),
            "fonte_url": a.get("fonte_url"),
            "score": round(a.get("rrf_score", 0.0), 4),
        }
        for a in mesclados
    ]

    return {
        "status": "sucesso",
        "detalhe": (
            f"{len(acordaos)} acordao(s) selecionado(s) via hibrida "
            f"(semantica={len(semanticos)}, lexical={len(lexicais)})"
        ),
        "acordaos": acordaos,
        "total": len(acordaos),
    }
