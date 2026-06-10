"""Utilitarios de autenticacao/sessao para rotas FastAPI."""

import hashlib
import hmac
import json
import logging
import os
import time
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Header, HTTPException, Request, Response, status

from App.database import get_sessao_ativa

logger = logging.getLogger(__name__)

# Nome do cookie de sessao enviado ao navegador.
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "contestacao_session")

# Configuracoes para endurecer sessao em producao sem quebrar ambiente local.
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()
SESSION_COOKIE_SECURE = (
    os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"
)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_PUBLISHABLE_KEY = (
    os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
).strip()

try:
    SUPABASE_AUTH_TIMEOUT_SECONDS = int(os.getenv("SUPABASE_AUTH_TIMEOUT_SECONDS", "8"))
except ValueError:
    SUPABASE_AUTH_TIMEOUT_SECONDS = 8

# Cache para validacao de bearer tokens do Supabase.
# Evita HTTP round-trip ao Supabase a cada request autenticada.
# TTL curto (30s) garante que revogacoes sao refletidas rapidamente.
_SUPABASE_CACHE_TTL = 30.0
# PR8 P2.2 — cap no tamanho do cache para evitar crescimento ilimitado com
# muitos tokens unicos. Sem isso, processo de longa duracao consome RAM crescente.
_SUPABASE_CACHE_MAX_ENTRIES = int(os.getenv("SUPABASE_CACHE_MAX_ENTRIES", "500"))
_supabase_token_cache: dict[str, tuple[float, dict[str, str] | None]] = {}
_supabase_token_cache_lock = threading.Lock()


def _supabase_cache_key(token: str) -> str:
    """Usa SHA-256 do token como chave — nunca armazena o token em claro."""
    return hashlib.sha256(token.encode()).hexdigest()


def _get_cached_supabase_user(token: str) -> tuple[bool, dict[str, str] | None]:
    """Retorna (hit, user). hit=True se encontrou no cache (mesmo que user=None)."""
    key = _supabase_cache_key(token)
    with _supabase_token_cache_lock:
        entry = _supabase_token_cache.get(key)
        if entry and entry[0] > time.monotonic():
            return True, entry[1]
    return False, None


def _set_cached_supabase_user(token: str, user: dict[str, str] | None) -> None:
    key = _supabase_cache_key(token)
    expires = time.monotonic() + _SUPABASE_CACHE_TTL
    with _supabase_token_cache_lock:
        # PR8 P2.2 — eviction: se cache no limite, remove entradas expiradas
        # antes de inserir. Sem deslocar para LRU completo — simples e suficiente
        # com TTL de 30s (entradas tendem a expirar rapido).
        if len(_supabase_token_cache) >= _SUPABASE_CACHE_MAX_ENTRIES:
            agora = time.monotonic()
            expiradas = [
                k for k, (exp, _) in _supabase_token_cache.items() if exp <= agora
            ]
            for k in expiradas:
                del _supabase_token_cache[k]
        _supabase_token_cache[key] = (expires, user)


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extrai token de um header Authorization no formato Bearer."""
    if not authorization:
        return None

    raw_value = authorization.strip()
    if not raw_value.lower().startswith("bearer "):
        return None
    token = raw_value[7:].strip()
    return token or None


def extract_session_token(request: Request, authorization: str | None) -> str | None:
    """Prioriza Bearer token; fallback para cookie HTTPOnly de sessao."""
    bearer_token = _extract_bearer_token(authorization)
    if bearer_token:
        return bearer_token

    cookie_token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    return cookie_token or None


def apply_session_cookie(response: Response, token: str) -> None:
    """Aplica cookie de sessao no response de login/cadastro.

    PR8 P2.3: usa `max_age` baseado em SESSION_TTL_HOURS. Sem isso, o cookie
    e de sessao (expira ao fechar o browser) mesmo que a sessao no banco
    dure 12h — usuario perdia sessao desnecessariamente ao fechar laptop.
    """
    ttl_segundos = int(os.getenv("SESSION_TTL_HOURS", "12")) * 3600
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
        max_age=ttl_segundos,
    )


def clear_session_cookie(response: Response) -> None:
    """Remove cookie de sessao no logout."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )


def _build_supabase_user(user_data: dict[str, Any]) -> dict[str, str] | None:
    user_id = str(user_data.get("id") or "").strip()
    email = str(user_data.get("email") or "").strip().lower()
    if not user_id or not email:
        return None

    metadata = user_data.get("user_metadata")
    metadata_name = ""
    if isinstance(metadata, dict):
        metadata_name = str(
            metadata.get("name") or metadata.get("full_name") or ""
        ).strip()

    nome = metadata_name or email.split("@", 1)[0] or "Conta"
    return {
        "id": user_id,
        "nome": nome,
        "email": email,
        "auth_provider": "supabase",
    }


def validate_supabase_bearer_token(token: str) -> dict[str, str] | None:
    """Valida bearer token no Auth do Supabase e retorna perfil basico.

    Resultados sao cacheados por _SUPABASE_CACHE_TTL segundos para evitar
    HTTP round-trip ao Supabase em cada request autenticada.
    """
    if not SUPABASE_URL or not token:
        return None

    hit, cached_user = _get_cached_supabase_user(token)
    if hit:
        return cached_user

    request_headers = {
        "Authorization": f"Bearer {token}",
    }
    if SUPABASE_PUBLISHABLE_KEY:
        request_headers["apikey"] = SUPABASE_PUBLISHABLE_KEY

    request = UrlRequest(
        url=f"{SUPABASE_URL}/auth/v1/user",
        headers=request_headers,
        method="GET",
    )

    try:
        with urlopen(request, timeout=SUPABASE_AUTH_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as error:
        if error.code in {401, 403}:
            # Token rejeitado pelo Supabase: cacheia None para evitar retry
            # imediato. NUNCA logamos o token em si.
            logger.info("Supabase rejeitou bearer token (status=%s)", error.code)
            _set_cached_supabase_user(token, None)
            return None
        logger.error(
            "Erro HTTP ao validar token no Supabase: status=%s msg=%s",
            error.code,
            error.reason,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falha ao validar token no Supabase.",
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        logger.error(
            "Indisponibilidade ao consultar Supabase Auth: %s: %s",
            type(error).__name__,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nao foi possivel validar autenticacao no Supabase.",
        ) from error

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning(
            "Resposta nao-JSON do Supabase Auth: %s",
            type(error).__name__,
        )
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "Resposta inesperada do Supabase Auth (tipo=%s)", type(payload).__name__
        )
        return None

    user = _build_supabase_user(payload)
    _set_cached_supabase_user(token, user)
    return user


def _validate_backend_admin_token(bearer_token: str) -> dict[str, str] | None:
    """PR16 Bug #1 fix: aceita BACKEND_ADMIN_TOKEN compartilhado n8n -> backend.

    Quando o workflow n8n chama /api/rag/defesas-similares ou
    /api/legislacao/buscar internamente (dentro da rede Docker), nao tem
    sessao de usuario nem JWT — autentica via Bearer com o token configurado
    no docker-compose. Token de 32 hex (256 bits) eh nao-brute-forceable.

    Retorna pseudo-user 'system:n8n' que satisfaz a assinatura do callback.
    """
    admin_token = os.getenv("BACKEND_ADMIN_TOKEN", "").strip()
    # compare_digest: comparacao em tempo constante — `!=` permitiria timing
    # attack pra reconstruir o token byte a byte.
    if not admin_token or not hmac.compare_digest(bearer_token, admin_token):
        return None
    return {
        "id": "system:n8n",
        "nome": "Sistema n8n (chamada interna do workflow)",
        "email": "system@autojuri.internal",
        "auth_provider": "backend_admin_token",
    }


async def get_authenticated_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Dependencia FastAPI para bloquear rotas sem sessao valida."""
    token = extract_session_token(request, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacao obrigatoria para este endpoint.",
        )

    bearer_token = _extract_bearer_token(authorization)
    if bearer_token:
        # PR16 Bug #1: tenta primeiro o admin token compartilhado com o n8n.
        admin_user = _validate_backend_admin_token(bearer_token)
        if admin_user:
            return admin_user

        # Compatibilidade: aceita token opaco legado ou JWT do Supabase no header.
        try:
            session = get_sessao_ativa(bearer_token)
        except (RuntimeError, OSError, ValueError) as err:
            # DB indisponivel ou token mal formado: continua tentando Supabase.
            logger.warning(
                "Sessao local indisponivel (%s); tentando validacao Supabase.",
                type(err).__name__,
            )
            session = None
        if session:
            return session

        supabase_user = validate_supabase_bearer_token(bearer_token)
        if supabase_user:
            return supabase_user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao invalida ou expirada. Faca login novamente.",
        )

    # Caminho cookie: mesmo tratamento de DB indisponivel do caminho Bearer —
    # sem isso, erro de infra virava 500 generico em vez de 503 explicito.
    try:
        session = get_sessao_ativa(token)
    except (RuntimeError, OSError, ValueError) as err:
        logger.warning(
            "Sessao local indisponivel ao validar cookie (%s).",
            type(err).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nao foi possivel validar a sessao. Tente novamente.",
        ) from err
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao invalida ou expirada. Faca login novamente.",
        )

    return session
