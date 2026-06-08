"""Rota POST /api/legislacao/buscar — busca hibrida em public.legislacao (PR13 #B3).

Consumida pelo workflow contestar-por-peticao (novo node "Buscar Legislacao
Aplicavel" entre "Buscar Defesas Anteriores" e "Claude Gerador"). Retorna leis,
artigos e sumulas verbatim pra serem injetados no SYSTEM_GERACAO, eliminando
alucinacao de citacoes na origem.

Mesmo desenho do RAG hibrido de contestacoes (rag.py):
- semantica via pgvector (embedding query gerada com sentence-transformers)
- lexical via ts_rank_cd + plainto_tsquery('portuguese')
- mescla via Reciprocal Rank Fusion (k=60)

Diferenca: sem multi-tenant (legislacao eh recurso compartilhado) e sem rerank
por feedback (lei nao tem feedback humano — eh fato juridico).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from App.database import buscar_legislacao_lexical, buscar_legislacao_semantica
from App.limiter import limiter
from App.security import get_authenticated_user
from App.services.embedding_service import gerar_embedding_query

logger = logging.getLogger(__name__)
router = APIRouter()

# Mesma constante do rag.py — RRF clássico Cormack et al 2009.
_RRF_K = 60
_CANDIDATOS_POR_BUSCA = 8
_TOP_N_FINAL = 5  # quantos artigos injetar no Gerador (cap de tokens)


def _resposta_vazia(status_code: str, detalhe: str) -> dict:
    return {"status": status_code, "detalhe": detalhe, "leis": [], "total": 0}


def _normalizar_input(payload: dict) -> tuple[str, str | None]:
    """Extrai (texto_query, area_juridica) do payload."""
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
    return texto_query, area_juridica


def _executar_semantica(
    embedding: list[float] | None, area_juridica: str | None
) -> list[dict]:
    if embedding is None:
        return []
    try:
        return buscar_legislacao_semantica(
            embedding=embedding,
            area_juridica=area_juridica,
            limit=_CANDIDATOS_POR_BUSCA,
        )
    except Exception as err:
        logger.error("Falha na busca semantica de legislacao area=%s erro=%s", area_juridica, err)
        return []


def _executar_lexical(texto_query: str, area_juridica: str | None) -> list[dict]:
    try:
        return buscar_legislacao_lexical(
            texto_query=texto_query,
            area_juridica=area_juridica,
            limit=_CANDIDATOS_POR_BUSCA,
        )
    except Exception as err:
        logger.error("Falha na busca lexical de legislacao area=%s erro=%s", area_juridica, err)
        return []


def _mesclar_rrf(
    semanticos: list[dict], lexicais: list[dict]
) -> list[dict]:
    """RRF sobre (origem, numero) — chave unica em public.legislacao."""
    rrf_scores: dict[tuple[str, str], float] = {}
    leis_por_chave: dict[tuple[str, str], dict] = {}

    for idx, lei in enumerate(semanticos, start=1):
        chave = (lei.get("origem", ""), lei.get("numero", ""))
        rrf_scores[chave] = rrf_scores.get(chave, 0.0) + 1.0 / (_RRF_K + idx)
        leis_por_chave.setdefault(chave, lei)

    for idx, lei in enumerate(lexicais, start=1):
        chave = (lei.get("origem", ""), lei.get("numero", ""))
        rrf_scores[chave] = rrf_scores.get(chave, 0.0) + 1.0 / (_RRF_K + idx)
        leis_por_chave.setdefault(chave, lei)

    resultado = []
    for chave, score in rrf_scores.items():
        lei = dict(leis_por_chave[chave])
        lei["rrf_score"] = score * (_RRF_K + 1)
        resultado.append(lei)
    resultado.sort(key=lambda l: l["rrf_score"], reverse=True)
    return resultado[:_TOP_N_FINAL]


@router.post("/legislacao/buscar")
@limiter.limit("60/minute")
async def buscar_legislacao(
    request: Request,
    payload: dict = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Busca leis/sumulas relevantes via hibrida (vetorial + lexical + RRF).

    Payload:
        fatos: str           — resumo dos fatos extraidos (opcional)
        pedidos: list|str    — pedidos do autor
        tese_central: str    — tese gerada (opcional, refina query)
        area_juridica: str   — filtro opcional (trabalhista|consumidor|...)

    Retorna top 5 leis com {origem, numero, texto, area_juridica, score} pra
    serem injetadas verbatim no prompt do Gerador.
    """
    texto_query, area_juridica = _normalizar_input(payload)

    if not texto_query:
        return _resposta_vazia(
            "sem_texto", "fatos, pedidos e tese vazios — nao e possivel buscar"
        )

    embedding = gerar_embedding_query(texto_query)
    if embedding is None:
        logger.info("Busca legislacao sem embedding — caindo em lexical-only")

    semanticos = _executar_semantica(embedding, area_juridica)
    lexicais = _executar_lexical(texto_query, area_juridica)

    if not semanticos and not lexicais:
        return _resposta_vazia(
            "sem_resultados", "Nenhuma legislacao encontrada para esta query."
        )

    mesclados = _mesclar_rrf(semanticos, lexicais)
    leis = [
        {
            "origem": l["origem"],
            "numero": l["numero"],
            "texto": l["texto"],
            "area_juridica": l.get("area_juridica"),
            "score": round(l.get("rrf_score", 0.0), 4),
        }
        for l in mesclados
    ]

    return {
        "status": "sucesso",
        "detalhe": (
            f"{len(leis)} lei(s) selecionada(s) via hibrida "
            f"(semantica={len(semanticos)}, lexical={len(lexicais)})"
        ),
        "leis": leis,
        "total": len(leis),
    }
