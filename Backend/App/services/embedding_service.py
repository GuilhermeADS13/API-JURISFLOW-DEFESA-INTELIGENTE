"""Servico de embeddings semanticos para RAG (PR6 #4 - Guia v3 §2.3).

Dois providers suportados (mesma dimensao 1024 para schema compartilhado):
  cohere  — embed-multilingual-v3.0, 1024 dims, $0.10/1M tokens (default)
  openai  — text-embedding-3-small com dimensions=1024, $0.13/1M tokens

Configuracao via env:
    EMBEDDING_PROVIDER=cohere|openai   (default: cohere)
    COHERE_API_KEY=...                 (se provider=cohere)
    OPENAI_API_KEY=...                 (se provider=openai)

Se a chave nao estiver configurada ou a lib nao instalada, gerar_embedding()
retorna None silenciosamente. O fluxo continua com TF-IDF no n8n como fallback.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024
_COHERE_MODEL = "embed-multilingual-v3.0"
_OPENAI_MODEL = "text-embedding-3-small"
_MAX_CHARS = 8192


def _provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "cohere").strip().lower()


def gerar_embedding(texto: str) -> Optional[list[float]]:
    """Gera embedding de 1024 dims para o texto.

    Retorna None se provider nao configurado, chave ausente ou erro de API.
    """
    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        return None

    provider = _provider()
    if provider == "cohere":
        return _gerar_cohere(texto_limpo)
    if provider == "openai":
        return _gerar_openai(texto_limpo)

    logger.debug("EMBEDDING_PROVIDER '%s' nao reconhecido. RAG semantico desativado.", provider)
    return None


# ── Cohere ────────────────────────────────────────────────────────────────────

def _gerar_cohere(texto: str) -> Optional[list[float]]:
    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key:
        logger.debug("COHERE_API_KEY ausente. RAG semantico desativado.")
        return None

    try:
        import cohere  # type: ignore[import]
    except ImportError:
        logger.warning(
            "Pacote 'cohere' nao instalado. "
            "Instale com: pip install 'cohere>=5,<6'"
        )
        return None

    try:
        client = cohere.Client(api_key)
        resp = client.embed(
            texts=[texto[:_MAX_CHARS]],
            model=_COHERE_MODEL,
            input_type="search_document",
        )
        emb = resp.embeddings[0] if resp.embeddings else []
        if len(emb) != EMBEDDING_DIM:
            logger.warning(
                "Cohere retornou embedding com %d dims (esperado %d).",
                len(emb),
                EMBEDDING_DIM,
            )
            return None
        return [float(v) for v in emb]
    except Exception as err:
        logger.error("Erro ao gerar embedding Cohere: %s", err)
        return None


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _gerar_openai(texto: str) -> Optional[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.debug("OPENAI_API_KEY ausente. RAG semantico desativado.")
        return None

    try:
        import openai  # type: ignore[import]
    except ImportError:
        logger.warning(
            "Pacote 'openai' nao instalado. "
            "Instale com: pip install 'openai>=1'"
        )
        return None

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.embeddings.create(
            model=_OPENAI_MODEL,
            input=texto[:_MAX_CHARS],
            dimensions=EMBEDDING_DIM,
        )
        emb = resp.data[0].embedding if resp.data else []
        if len(emb) != EMBEDDING_DIM:
            logger.warning(
                "OpenAI retornou embedding com %d dims (esperado %d).",
                len(emb),
                EMBEDDING_DIM,
            )
            return None
        return [float(v) for v in emb]
    except Exception as err:
        logger.error("Erro ao gerar embedding OpenAI: %s", err)
        return None


# ── Query embedding (input_type diferente no Cohere) ─────────────────────────

def gerar_embedding_query(texto: str) -> Optional[list[float]]:
    """Gera embedding para uma query de busca (vs documento).

    Cohere distingue input_type='search_query' de 'search_document'.
    OpenAI nao faz essa distincao — redireciona para gerar_embedding.
    """
    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        return None

    provider = _provider()
    if provider != "cohere":
        return gerar_embedding(texto_limpo)

    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import cohere  # type: ignore[import]
        client = cohere.Client(api_key)
        resp = client.embed(
            texts=[texto_limpo[:_MAX_CHARS]],
            model=_COHERE_MODEL,
            input_type="search_query",
        )
        emb = resp.embeddings[0] if resp.embeddings else []
        if len(emb) != EMBEDDING_DIM:
            return None
        return [float(v) for v in emb]
    except Exception as err:
        logger.error("Erro ao gerar query embedding Cohere: %s", err)
        return None
