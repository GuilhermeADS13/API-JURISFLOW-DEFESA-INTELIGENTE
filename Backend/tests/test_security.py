"""Testes dos utilitarios de seguranca/autenticacao."""

import asyncio

import pytest
from fastapi import HTTPException, Request, Response

from App import security


def _request_com_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/usuarios/sessao",
        "headers": headers,
    }
    return Request(scope)


@pytest.mark.parametrize(
    "authorization,esperado",
    [
        ("Bearer token123", "token123"),
        ("bearer abc", "abc"),
        ("Bearer    token-spaces", "token-spaces"),
        ("Token invalido", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_bearer_token(authorization, esperado):
    assert security._extract_bearer_token(authorization) == esperado


def test_extract_session_token_prioriza_bearer():
    request = _request_com_headers([(b"cookie", b"contestacao_session=cookie-token")])
    token = security.extract_session_token(request, "Bearer header-token")
    assert token == "header-token"


def test_extract_session_token_fallback_cookie():
    cookie_header = f"{security.SESSION_COOKIE_NAME}=cookie-token".encode("utf-8")
    request = _request_com_headers([(b"cookie", cookie_header)])
    token = security.extract_session_token(request, None)
    assert token == "cookie-token"


def test_apply_e_clear_cookie():
    response = Response()
    security.apply_session_cookie(response, "token-abc")
    set_cookie_header = response.headers.get("set-cookie", "")
    assert security.SESSION_COOKIE_NAME in set_cookie_header
    assert "httponly" in set_cookie_header.lower()

    security.clear_session_cookie(response)
    clear_cookie_header = response.headers.get("set-cookie", "")
    assert security.SESSION_COOKIE_NAME in clear_cookie_header


def test_apply_cookie_inclui_max_age_baseado_em_session_ttl(monkeypatch):
    """PR8 P2.3 — cookie deve ter Max-Age para persistir entre fechamentos do browser."""
    monkeypatch.setenv("SESSION_TTL_HOURS", "12")
    response = Response()
    security.apply_session_cookie(response, "token-xyz")
    set_cookie_header = response.headers.get("set-cookie", "").lower()
    # 12h * 3600 = 43200 segundos
    assert "max-age=43200" in set_cookie_header


def test_apply_cookie_respeita_session_ttl_customizado(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_HOURS", "2")
    response = Response()
    security.apply_session_cookie(response, "token-y")
    set_cookie_header = response.headers.get("set-cookie", "").lower()
    # 2h * 3600 = 7200
    assert "max-age=7200" in set_cookie_header


def test_supabase_cache_eviction_remove_expiradas_no_limite(monkeypatch):
    """PR8 P2.2 — quando cache atinge MAX_ENTRIES, remove entradas expiradas antes de inserir."""
    monkeypatch.setattr(security, "_SUPABASE_CACHE_MAX_ENTRIES", 3)
    # Limpa cache
    security._supabase_token_cache.clear()

    # Insere 3 entradas expiradas (passado)
    import time

    agora = time.monotonic()
    security._supabase_token_cache["k1"] = (agora - 100, {"id": "1"})
    security._supabase_token_cache["k2"] = (agora - 50, {"id": "2"})
    security._supabase_token_cache["k3"] = (agora - 10, {"id": "3"})
    assert len(security._supabase_token_cache) == 3

    # Insere uma 4a — deve disparar eviction das 3 expiradas
    security._set_cached_supabase_user("token-novo", {"id": "novo"})

    # As 3 antigas foram removidas; so a nova permanece
    assert len(security._supabase_token_cache) == 1
    assert security._supabase_cache_key("token-novo") in security._supabase_token_cache


def test_get_authenticated_user_sem_token_retorna_401():
    request = _request_com_headers([])
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(security.get_authenticated_user(request, None))
    assert exc_info.value.status_code == 401


def test_get_authenticated_user_sessao_invalida(monkeypatch):
    request = _request_com_headers([])
    monkeypatch.setattr(security, "extract_session_token", lambda req, auth: "token-x")
    monkeypatch.setattr(security, "get_sessao_ativa", lambda token: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(security.get_authenticated_user(request, None))
    assert exc_info.value.status_code == 401


def test_get_authenticated_user_fluxo_feliz(monkeypatch):
    request = _request_com_headers([])
    fake_session = {
        "id": "USR-001",
        "nome": "Ana",
        "email": "ana@teste.com",
        "token": "abc",
    }

    monkeypatch.setattr(security, "extract_session_token", lambda req, auth: "token-ok")
    monkeypatch.setattr(security, "get_sessao_ativa", lambda token: fake_session)

    result = asyncio.run(security.get_authenticated_user(request, None))
    assert result == fake_session


def test_get_authenticated_user_valida_bearer_supabase(monkeypatch):
    request = _request_com_headers([])
    supabase_user = {
        "id": "d20fdacb-4f53-4f9a-a280-2e16cb5ab6f7",
        "nome": "Ana",
        "email": "ana@teste.com",
        "auth_provider": "supabase",
    }

    monkeypatch.setattr(security, "get_sessao_ativa", lambda token: None)
    monkeypatch.setattr(
        security, "validate_supabase_bearer_token", lambda token: supabase_user
    )

    result = asyncio.run(
        security.get_authenticated_user(
            request=request,
            authorization="Bearer jwt-token-de-teste",
        )
    )

    assert result == supabase_user


def test_get_authenticated_user_bearer_invalido_retorna_401(monkeypatch):
    request = _request_com_headers([])

    monkeypatch.setattr(security, "get_sessao_ativa", lambda token: None)
    monkeypatch.setattr(security, "validate_supabase_bearer_token", lambda token: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            security.get_authenticated_user(
                request=request,
                authorization="Bearer jwt-token-invalido",
            )
        )

    assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# PR16 Bug #1 — BACKEND_ADMIN_TOKEN aceito como pseudo-user 'system:n8n'
# ─────────────────────────────────────────────────────────────────────────────


def test_backend_admin_token_autentica_chamada_interna_n8n(monkeypatch):
    """n8n chama /api/rag e /api/legislacao via Bearer com BACKEND_ADMIN_TOKEN."""
    monkeypatch.setenv("BACKEND_ADMIN_TOKEN", "token-do-n8n-32hex")
    request = _request_com_headers([])

    # Mocka sessao + Supabase como invalidos (so o admin token deve passar)
    monkeypatch.setattr(security, "get_sessao_ativa", lambda token: None)
    monkeypatch.setattr(security, "validate_supabase_bearer_token", lambda token: None)

    result = asyncio.run(
        security.get_authenticated_user(
            request=request,
            authorization="Bearer token-do-n8n-32hex",
        )
    )

    assert result["id"] == "system:n8n"
    assert result["auth_provider"] == "backend_admin_token"


def test_backend_admin_token_errado_nao_autentica(monkeypatch):
    """Token diferente do BACKEND_ADMIN_TOKEN cai no fluxo Supabase normal."""
    monkeypatch.setenv("BACKEND_ADMIN_TOKEN", "token-correto-32hex")
    request = _request_com_headers([])

    monkeypatch.setattr(security, "get_sessao_ativa", lambda token: None)
    monkeypatch.setattr(security, "validate_supabase_bearer_token", lambda token: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            security.get_authenticated_user(
                request=request,
                authorization="Bearer token-errado",
            )
        )

    assert exc_info.value.status_code == 401


def test_backend_admin_token_vazio_no_env_nao_libera_nada(monkeypatch):
    """Se BACKEND_ADMIN_TOKEN nao tiver env (ou for vazio), helper retorna None
    e nao da bypass — defesa em profundidade."""
    monkeypatch.delenv("BACKEND_ADMIN_TOKEN", raising=False)

    # Bearer vazio NUNCA deve dar match com env vazio
    assert security._validate_backend_admin_token("") is None
    assert security._validate_backend_admin_token("qualquer-token") is None

    monkeypatch.setenv("BACKEND_ADMIN_TOKEN", "")
    assert security._validate_backend_admin_token("") is None
