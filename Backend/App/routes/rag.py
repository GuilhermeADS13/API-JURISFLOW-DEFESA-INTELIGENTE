"""Rota POST /api/rag/defesas-similares — RAG semantico com pgvector (PR6 #4).

Chamada pelo workflow n8n (node Buscar Defesas Anteriores) como alternativa
semantica ao TF-IDF. Aceita o mesmo token de sessao usado pelas rotas /admin/*.

Fluxo:
1. Recebe {fatos, pedidos, tipo_acao, numero_processo} do n8n
2. Concatena fatos + pedidos e gera embedding via embedding_service
3. Consulta pgvector (<=>) para os 10 casos mais proximos em coseno
4. Aplica reranking com feedback (0.6 * similaridade + 0.4 * feedback_util)
5. Retorna top 3 no mesmo shape que o node TF-IDF — compatibilidade garantida

Se embedding_service retornar None (provider sem chave), responde com
status='embedding_indisponivel' e o n8n cai no fallback TF-IDF local.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from App.database import buscar_defesas_semanticas
from App.limiter import limiter
from App.security import get_authenticated_user
from App.services.embedding_service import gerar_embedding_query

logger = logging.getLogger(__name__)
router = APIRouter()

_FEEDBACK_SCORE = {True: 1.0, False: 0.0, None: 0.5}


def _resposta_vazia(status_code: str, detalhe: str) -> dict:
    return {"status": status_code, "detalhe": detalhe, "casos": [], "total": 0}


def _normalizar_input(payload: dict) -> tuple[str, str, str]:
    """Extrai (tipo_acao, numero_processo, texto_query) do payload n8n."""
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
    return tipo_acao, numero_processo, texto_query


def _executar_busca_semantica(
    embedding: list[float],
    tipo_acao: str,
    numero_processo: str,
    usuario_id: str | None,
) -> tuple[list[dict] | None, dict | None]:
    """Executa a busca pgvector. Retorna (rows, None) em sucesso ou (None, resposta_erro)."""
    try:
        rows = buscar_defesas_semanticas(
            embedding=embedding,
            tipo_acao=tipo_acao,
            excluir_numero=numero_processo,
            limit=10,
        )
    except Exception as err:
        logger.error(
            "Falha na busca semantica pgvector tipo_acao=%s usuario_id=%s erro=%s",
            tipo_acao,
            usuario_id,
            err,
        )
        return None, _resposta_vazia("erro_busca", str(err)[:200])
    return rows, None


def _rerankear_e_montar_casos(rows: list[dict]) -> list[dict]:
    """Aplica reranking (0.6 similarity + 0.4 feedback) e retorna top 3 formatados."""
    for row in rows:
        fb_score = _FEEDBACK_SCORE.get(row.get("feedback_util"), 0.5)
        row["_score"] = 0.6 * row["similarity"] + 0.4 * fb_score
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
            "similarity": round(c["similarity"], 4),
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
    """Busca defesas anteriores semanticamente similares via pgvector.

    Retorna shape identico ao node TF-IDF do n8n para compatibilidade total.

    Payload esperado:
        tipo_acao: str        — obrigatorio
        numero_processo: str  — processo atual a excluir da busca
        fatos: str            — resumo dos fatos extraidos
        pedidos: str|list     — pedidos do autor (string ou lista)
    """
    tipo_acao, numero_processo, texto_query = _normalizar_input(payload)

    if not tipo_acao:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tipo_acao e obrigatorio.",
        )

    if not texto_query:
        return _resposta_vazia(
            "sem_texto", "fatos e pedidos vazios — nao e possivel gerar embedding"
        )

    # Gera embedding para a query (input_type='search_query' no Cohere)
    embedding = gerar_embedding_query(texto_query)
    if embedding is None:
        return _resposta_vazia(
            "embedding_indisponivel",
            (
                "Provider de embeddings nao configurado ou chave ausente. "
                "Configure EMBEDDING_PROVIDER + COHERE_API_KEY (ou OPENAI_API_KEY)."
            ),
        )

    rows, erro = _executar_busca_semantica(
        embedding, tipo_acao, numero_processo, usuario.get("id")
    )
    if erro is not None:
        return erro

    if not rows:
        return _resposta_vazia(
            "sem_resultados",
            "Nenhuma defesa anterior com embedding para este tipo_acao.",
        )

    casos = _rerankear_e_montar_casos(rows)

    return {
        "status": "sucesso",
        "detalhe": f"{len(casos)} defesa(s) semanticamente similares de {len(rows)} candidatas",
        "casos": casos,
        "total": len(casos),
    }
