"""Servico de embeddings semanticos para RAG (PR6 #4 - Guia v3 §2.3).

Tres providers suportados:
  local   - sentence-transformers paraphrase-multilingual-MiniLM-L12-v2, 384 dims (default)
            Roda no proprio container, sem chamada externa, sem custo.
  cohere  - embed-multilingual-v3.0, 1024 dims (deprecated — schema usa 384)
  openai  - text-embedding-3-small, 1024 dims (deprecated — schema usa 384)

Para usar cohere/openai o schema do banco precisa voltar para vector(1024).
A migracao default usa vector(384) para casar com o modelo local.

Configuracao via env:
    EMBEDDING_PROVIDER=local|cohere|openai   (default: local)
    EMBEDDING_MODEL=...                      (override do modelo local)
    HF_HOME=/app/hf_cache                    (cache do modelo no volume Docker)

Se a lib nao estiver instalada ou houver erro, gerar_embedding() retorna None
silenciosamente e o n8n cai para o fallback TF-IDF.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_COHERE_MODEL = "embed-multilingual-v3.0"
_OPENAI_MODEL = "text-embedding-3-small"
_MAX_CHARS = 8192

# Cache do modelo local — carrega 1x por processo (118MB).
_LOCAL_MODEL: Optional[Any] = None
_LOCAL_MODEL_LOCK = threading.Lock()


def _provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()


def gerar_embedding(texto: str) -> Optional[list[float]]:
    """Gera embedding para o texto.

    Default: provider local com sentence-transformers (384 dims).
    Retorna None se provider inacessivel — RAG cai para TF-IDF no n8n.
    """
    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        return None

    provider = _provider()
    if provider == "local":
        return _gerar_local(texto_limpo)
    if provider == "cohere":
        return _gerar_cohere(texto_limpo)
    if provider == "openai":
        return _gerar_openai(texto_limpo)

    logger.debug("EMBEDDING_PROVIDER '%s' nao reconhecido. RAG semantico desativado.", provider)
    return None


def gerar_embedding_query(texto: str) -> Optional[list[float]]:
    """Gera embedding para uma query de busca.

    No provider local, query e documento usam o mesmo modelo simetricamente.
    No Cohere, distingue input_type='search_query' vs 'search_document'.
    OpenAI nao faz distincao.
    """
    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        return None

    provider = _provider()
    if provider == "cohere":
        return _gerar_cohere_query(texto_limpo)
    return gerar_embedding(texto_limpo)


# ── Local (sentence-transformers) ─────────────────────────────────────────────

def _carregar_modelo_local() -> Optional[Any]:
    """Carrega o modelo sentence-transformers 1x e mantem em memoria."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is not None:
        return _LOCAL_MODEL

    with _LOCAL_MODEL_LOCK:
        if _LOCAL_MODEL is not None:
            return _LOCAL_MODEL

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
        except ImportError:
            logger.warning(
                "Pacote 'sentence-transformers' nao instalado. "
                "Instale com: pip install 'sentence-transformers>=3,<4'"
            )
            return None

        model_name = os.getenv("EMBEDDING_MODEL", _DEFAULT_LOCAL_MODEL)
        try:
            logger.info("Carregando modelo de embedding local: %s", model_name)
            _LOCAL_MODEL = SentenceTransformer(model_name)
            logger.info("Modelo de embedding carregado (dim=%d).", _LOCAL_MODEL.get_sentence_embedding_dimension())
        except Exception as err:
            logger.error("Falha ao carregar modelo local '%s': %s", model_name, err)
            return None

    return _LOCAL_MODEL


def _gerar_local(texto: str) -> Optional[list[float]]:
    model = _carregar_modelo_local()
    if model is None:
        return None

    try:
        emb = model.encode(texto[:_MAX_CHARS], normalize_embeddings=True)
        vetor = [float(v) for v in emb.tolist()]
        if len(vetor) != EMBEDDING_DIM:
            logger.warning(
                "Modelo local retornou embedding com %d dims (esperado %d).",
                len(vetor),
                EMBEDDING_DIM,
            )
            return None
        return vetor
    except Exception as err:
        logger.error("Erro ao gerar embedding local: %s", err)
        return None


# ── Cohere (legacy — 1024 dims, incompativel com schema atual) ────────────────

def _gerar_cohere(texto: str) -> Optional[list[float]]:
    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key:
        logger.debug("COHERE_API_KEY ausente. RAG semantico desativado.")
        return None

    try:
        import cohere  # type: ignore[import]
    except ImportError:
        logger.warning(
            "Pacote 'cohere' nao instalado. Instale com: pip install 'cohere>=5,<6'"
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
        return [float(v) for v in emb] if emb else None
    except Exception as err:
        logger.error("Erro ao gerar embedding Cohere: %s", err)
        return None


def _gerar_cohere_query(texto: str) -> Optional[list[float]]:
    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import cohere  # type: ignore[import]
        client = cohere.Client(api_key)
        resp = client.embed(
            texts=[texto[:_MAX_CHARS]],
            model=_COHERE_MODEL,
            input_type="search_query",
        )
        emb = resp.embeddings[0] if resp.embeddings else []
        return [float(v) for v in emb] if emb else None
    except Exception as err:
        logger.error("Erro ao gerar query embedding Cohere: %s", err)
        return None


# ── OpenAI (legacy — 1024 dims, incompativel com schema atual) ────────────────

def _gerar_openai(texto: str) -> Optional[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.debug("OPENAI_API_KEY ausente. RAG semantico desativado.")
        return None

    try:
        import openai  # type: ignore[import]
    except ImportError:
        logger.warning(
            "Pacote 'openai' nao instalado. Instale com: pip install 'openai>=1'"
        )
        return None

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.embeddings.create(
            model=_OPENAI_MODEL,
            input=texto[:_MAX_CHARS],
            dimensions=1024,
        )
        emb = resp.data[0].embedding if resp.data else []
        return [float(v) for v in emb] if emb else None
    except Exception as err:
        logger.error("Erro ao gerar embedding OpenAI: %s", err)
        return None
