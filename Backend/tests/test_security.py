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
