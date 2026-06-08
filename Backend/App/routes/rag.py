"""Rota POST /api/rag/defesas-similares — RAG hibrido (vetorial + lexical) com RRF.

Chamada pelo workflow n8n (node Buscar Defesas Anteriores). Aceita o mesmo
token de sessao usado pelas rotas /admin/*.

PR12 #4 — Busca Hibrida (Guia v4):
- semantica (pgvector <=>): captura sinonimia / parafrase via embedding 384d.
- lexical (tsvector + ts_rank_cd): captura termos juridicos exatos (Sumulas,
  artigos, expressoes cristalizadas) que embeddings podem ranquear baixo.
- Reciprocal Rank Fusion (k=60): mescla os dois rankings por posicao, nao
  por score absoluto — robusto a escalas diferentes (cosine 0-1 vs ts_rank
  arbitrario).
- reranking final: 0.6 * rrf_normalizado + 0.4 * feedback_util.

Fluxo:
1. Recebe {fatos, pedidos, tipo_acao, numero_processo} do n8n.
2. Concatena fatos + pedidos -> texto_query.
3. Gera embedding via embedding_service (input_type='search_query' no Cohere).
4. Roda duas buscas (semantica + lexical), mescla via RRF.
5. Aplica reranking com feedback e retorna top 3 no mesmo shape do TF-IDF.

Se embedding_service retornar None, ainda assim devolve resultados lexicais
(a hibrida vira lexical-only). Se ambas as buscas vierem vazias, retorna
`status='sem_resultados'` e o n8n cai no fallback TF-IDF local.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from App.database import buscar_defesas_lexicais, buscar_defesas_semanticas
from App.limiter import limiter
from App.security import get_authenticated_user
from App.services.embedding_service import gerar_embedding_query

logger = logging.getLogger(__name__)
router = APIRouter()

_FEEDBACK_SCORE = {True: 1.0, False: 0.0, None: 0.5}

# RRF constante: 60 e o valor classico do paper original (Cormack et al, 2009).
# Maior k = ranking mais "achatado" (diferenca entre top-1 e top-10 menor),
# menor k = ranking mais "agressivo" (top-1 domina). 60 e bom default.
_RRF_K = 60

# Quantos candidatos pegar de CADA busca individual antes de mesclar.
# 10 e suficiente — RRF tipicamente nao move muita coisa pra cima da posicao 10.
_CANDIDATOS_POR_BUSCA = 10


def _resposta_vazia(status_code: str, detalhe: str) -> dict:
    return {"status": status_code, "detalhe": detalhe, "casos": [], "total": 0}


def _normalizar_input(payload: dict) -> tuple[str, str, str, str | None]:
    """Extrai (tipo_acao, numero_processo, texto_query, area_juridica) do payload n8n.

    `area_juridica` (PR13 #B1) eh opcional — quando vier, a busca filtra por
    ela alem do tipo_acao (mais especifico). None = sem filtro adicional.
    """
    tipo_acao = str(payload.get("tipo_acao") or "").strip()
    numero_processo = str(payload.get("numero_processo") or "sem-numero").strip()
    fatos = str(payload.get("fatos") or "").strip()
    pedidos_raw = payload.get("pedidos") or []
    pedidos_str = (
        " ".join(str(p) for p in pedidos_raw)
        if isinstance(pedidos_raw, list)
        else str(pedidos_raw)
    )
    texto_query = f"{fatos} {pedidos_str}".strip()
    area_raw = payload.get("area_juridica")
    area_juridica = str(area_raw).strip().lower() if area_raw else None
    return tipo_acao, numero_processo, texto_query, area_juridica


def _executar_busca_semantica(
    embedding: list[float] | None,
    tipo_acao: str,
    numero_processo: str,
    usuario_id: str | None,
    area_juridica: str | None,
) -> list[dict]:
    """Executa a busca pgvector. Retorna [] em erro (logado) ou se embedding=None."""
    if embedding is None:
        return []
    try:
        return buscar_defesas_semanticas(
            embedding=embedding,
            tipo_acao=tipo_acao,
            excluir_numero=numero_processo,
            usuario_id=usuario_id,
            limit=_CANDIDATOS_POR_BUSCA,
            area_juridica=area_juridica,
        )
    except Exception as err:
        logger.error(
            "Falha na busca semantica pgvector tipo_acao=%s usuario_id=%s erro=%s",
            tipo_acao,
            usuario_id,
            err,
        )
        return []


def _executar_busca_lexical(
    texto_query: str,
    tipo_acao: str,
    numero_processo: str,
    usuario_id: str | None,
    area_juridica: str | None,
) -> list[dict]:
    """Executa a busca lexical tsvector. Retorna [] em erro (logado)."""
    try:
        return buscar_defesas_lexicais(
            texto_query=texto_query,
            tipo_acao=tipo_acao,
            excluir_numero=numero_processo,
            usuario_id=usuario_id,
            limit=_CANDIDATOS_POR_BUSCA,
            area_juridica=area_juridica,
        )
    except Exception as err:
        logger.error(
            "Falha na busca lexical tsvector tipo_acao=%s usuario_id=%s erro=%s",
            tipo_acao,
            usuario_id,
            err,
        )
        return []


def _mesclar_rrf(
    semanticos: list[dict],
    lexicais: list[dict],
) -> list[dict]:
    """Mescla os dois rankings via Reciprocal Rank Fusion (k=60).

    RRF score por documento = sum(1 / (k + rank_i)) onde rank_i e a posicao
    1-indexed do documento na busca i (semantica e lexical). Documentos que
    aparecem em ambas listas ganham score combinado; documentos exclusivos de
    uma lista mantem score parcial.

    Chave de unicidade: `numero_processo` — funciona porque exemplares humanos
    podem repetir numero "sem-numero" mas tem id unico no banco; aqui esta OK
    misturar (estamos rankando por mesma combinacao tipo_acao + texto).
    Tradeoff aceitavel: 2 exemplares humanos com numero_processo igual seriam
    deduplicados — improvavel na pratica.
    """
    rrf_scores: dict[str, float] = {}
    casos_por_chave: dict[str, dict] = {}

    for idx, caso in enumerate(semanticos, start=1):
        chave = caso.get("numero_processo") or f"_sem_id_sem_{idx}"
        rrf_scores[chave] = rrf_scores.get(chave, 0.0) + 1.0 / (_RRF_K + idx)
        # Prefere o objeto da busca semantica como base (tem campo `similarity`).
        casos_por_chave.setdefault(chave, caso)

    for idx, caso in enumerate(lexicais, start=1):
        chave = caso.get("numero_processo") or f"_sem_id_lex_{idx}"
        rrf_scores[chave] = rrf_scores.get(chave, 0.0) + 1.0 / (_RRF_K + idx)
        casos_por_chave.setdefault(chave, caso)

    resultado: list[dict] = []
    for chave, rrf_score in rrf_scores.items():
        caso = casos_por_chave[chave]
        # Normaliza pra [0, 1] aproximadamente — k=60 e rank=1 da 1/61 ~ 0.016;
        # multiplicar por _RRF_K + 1 = 61 da 1.0. Quando o doc aparece nas duas,
        # o score normalizado pode passar de 1.0 — ok, a hierarquia importa.
        caso = dict(caso)  # nao mutar referencia das listas originais
        caso["_rrf_score"] = rrf_score * (_RRF_K + 1)
        # `similarity` mantem-se quando vem da semantica; senao usa rrf_score
        # como proxy (frontend/n8n esperam esse campo).
        if "similarity" not in caso:
            caso["similarity"] = caso["_rrf_score"]
        resultado.append(caso)

    return resultado


def _rerankear_e_montar_casos(rows: list[dict]) -> list[dict]:
    """Aplica reranking final (0.6 RRF + 0.4 feedback) e retorna top 3 formatados."""
    for row in rows:
        fb_score = _FEEDBACK_SCORE.get(row.get("feedback_util"), 0.5)
        # Em hibrida, `_rrf_score` ja existe. Em legado (so semantica), usa similarity.
        base_score = row.get("_rrf_score") or row.get("similarity", 0.0)
        row["_score"] = 0.6 * min(base_score, 1.0) + 0.4 * fb_score
    rows.sort(key=lambda r: r["_score"], reverse=True)

    return [
        {
            "numero_processo": c["numero_processo"],
            "tipo_acao": c["tipo_acao"],
            "fatos_resumo": c["fatos"][:500],
            "pedido_autor_resumo": c["pedido_autor"][:300],
            "tese_central": c["tese_central"],
            "resumo_estrategico": c["resumo_estrategico"],
            "fundamentos_curtos": c["fundamentos_curtos"],
            "riscos": c["riscos"],
            "criado_em": c["criado_em"],
            "similarity": round(c.get("similarity", 0.0), 4),
        }
        for c in rows[:3]
    ]


@router.post("/rag/defesas-similares")
@limiter.limit("30/minute")
async def buscar_defesas_similares(
    request: Request,
    payload: dict = Body(...),
    usuario: dict[str, str] = Depends(get_authenticated_user),
) -> dict:
    """Busca defesas anteriores via RAG hibrido (semantica + lexical via RRF).

    Retorna shape identico ao node TF-IDF do n8n para compatibilidade total.

    Payload esperado:
        tipo_acao: str        — obrigatorio
        numero_processo: str  — processo atual a excluir da busca
        fatos: str            — resumo dos fatos extraidos
        pedidos: str|list     — pedidos do autor (string ou lista)
    """
    tipo_acao, numero_processo, texto_query, area_juridica = _normalizar_input(payload)

    if not tipo_acao:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tipo_acao e obrigatorio.",
        )

    if not texto_query:
        return _resposta_vazia(
            "sem_texto", "fatos e pedidos vazios — nao e possivel buscar"
        )

    embedding = gerar_embedding_query(texto_query)
    if embedding is None:
        logger.info(
            "RAG hibrido sem embedding (provider sem chave) — caindo em lexical-only"
        )

    usuario_id = usuario.get("id")
    semanticos = _executar_busca_semantica(
        embedding, tipo_acao, numero_processo, usuario_id, area_juridica
    )
    lexicais = _executar_busca_lexical(
        texto_query, tipo_acao, numero_processo, usuario_id, area_juridica
    )

    if not semanticos and not lexicais:
        # Embeddings indisponiveis E lexical sem hits — sinaliza pro n8n cair em TF-IDF.
        if embedding is None:
            return _resposta_vazia(
                "embedding_indisponivel",
                (
                    "Provider de embeddings nao configurado E busca lexical sem hits. "
                    "Configure EMBEDDING_PROVIDER + COHERE_API_KEY (ou OPENAI_API_KEY)."
                ),
            )
        return _resposta_vazia(
            "sem_resultados",
            "Nenhuma defesa anterior encontrada para este tipo_acao.",
        )

    mesclados = _mesclar_rrf(semanticos, lexicais)
    casos = _rerankear_e_montar_casos(mesclados)

    return {
        "status": "sucesso",
        "detalhe": (
            f"{len(casos)} defesa(s) selecionadas via RAG hibrido "
            f"(semantica={len(semanticos)}, lexical={len(lexicais)}, "
            f"unicas={len(mesclados)})"
        ),
        "casos": casos,
        "total": len(casos),
    }
