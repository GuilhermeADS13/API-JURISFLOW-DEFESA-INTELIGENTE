"""Testes unitarios das rotas de autenticacao de usuario."""

import asyncio

import pytest
from fastapi import HTTPException, Request, Response

from App.database import DatabaseIntegrityError
from App.models.usuario import UsuarioCadastro, UsuarioLogin, UsuarioLogout
from App.routes import usuario


def _request_sem_headers() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/usuarios/logout",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 0),
    }
    return Request(scope)


def test_cadastrar_usuario_sucesso(monkeypatch):
    payload = UsuarioCadastro(
        name="Ana Silva", email="ana@teste.com", password="Senha@123"
    )
    response = Response()
    calls: dict = {}

    monkeypatch.setattr(usuario, "get_usuario_por_email", lambda email: None)
    monkeypatch.setattr(usuario, "hash_password", lambda senha: "hash-fixo")

    def fake_create_usuario(user_id, nome, email, senha_hash):
        calls["create_usuario"] = {
            "user_id": user_id,
            "nome": nome,
            "email": email,
            "senha_hash": senha_hash,
        }
        return {"id": "USR-001", "nome": nome, "email": email}

    monkeypatch.setattr(usuario, "create_usuario", fake_create_usuario)
    monkeypatch.setattr(usuario, "create_sessao_usuario", lambda user_id: "token-123")

    def fake_apply_session_cookie(resp, token):
        calls["cookie"] = {"token": token}
        resp.headers["X-Test-Token"] = token

    monkeypatch.setattr(usuario, "apply_session_cookie", fake_apply_session_cookie)

    result = asyncio.run(
        usuario.cadastrar_usuario(_request_sem_headers(), payload, response)
    )

    assert result["status"] == "sucesso"
    assert result["usuario"]["id"] == "USR-001"
    assert result["token"] == "token-123"
    assert calls["create_usuario"]["senha_hash"] == "hash-fixo"
    assert calls["cookie"]["token"] == "token-123"


def test_cadastrar_usuario_rejeita_email_duplicado(monkeypatch):
    payload = UsuarioCadastro(
        name="Ana Silva", email="ana@teste.com", password="Senha@123"
    )
    response = Response()

    monkeypatch.setattr(
        usuario,
        "get_usuario_por_email",
        lambda email: {"id": "USR-001", "nome": "Ana", "email": email},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            usuario.cadastrar_usuario(_request_sem_headers(), payload, response)
        )

    assert exc_info.value.status_code == 409


def test_cadastrar_usuario_trata_integridade(monkeypatch):
    payload = UsuarioCadastro(
        name="Ana Silva", email="ana@teste.com", password="Senha@123"
    )
    response = Response()

    monkeypatch.setattr(usuario, "get_usuario_por_email", lambda email: None)
    monkeypatch.setattr(usuario, "hash_password", lambda senha: "hash-fixo")

    def fake_create_usuario(*args, **kwargs):
        raise DatabaseIntegrityError("duplicado")

    monkeypatch.setattr(usuario, "create_usuario", fake_create_usuario)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            usuario.cadastrar_usuario(_request_sem_headers(), payload, response)
        )

    assert exc_info.value.status_code == 409


def test_login_rejeita_usuario_inexistente(monkeypatch):
    payload = UsuarioLogin(email="ana@teste.com", password="Senha@123")
    response = Response()
    monkeypatch.setattr(usuario, "get_usuario_por_email", lambda email: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(usuario.login_usuario(_request_sem_headers(), payload, response))

    assert exc_info.value.status_code == 401


def test_login_rejeita_senha_incorreta(monkeypatch):
    payload = UsuarioLogin(email="ana@teste.com", password="Senha@123")
    response = Response()
    monkeypatch.setattr(
        usuario,
        "get_usuario_por_email",
        lambda email: {
            "id": "USR-001",
            "nome": "Ana",
            "email": email,
            "senha_hash": "hash",
        },
    )
    monkeypatch.setattr(usuario, "verify_password", lambda senha, hash_: False)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(usuario.login_usuario(_request_sem_headers(), payload, response))

    assert exc_info.value.status_code == 401


def test_login_fluxo_feliz(monkeypatch):
    payload = UsuarioLogin(email="ana@teste.com", password="Senha@123")
    response = Response()
    calls: dict = {}

    monkeypatch.setattr(
        usuario,
        "get_usuario_por_email",
        lambda email: {
            "id": "USR-001",
            "nome": "Ana",
            "email": email,
            "senha_hash": "hash",
        },
    )
    monkeypatch.setattr(usuario, "verify_password", lambda senha, hash_: True)
    monkeypatch.setattr(usuario, "create_sessao_usuario", lambda user_id: "token-login")

    def fake_apply_session_cookie(resp, token):
        calls["cookie_token"] = token
        resp.headers["X-Test-Token"] = token

    monkeypatch.setattr(usuario, "apply_session_cookie", fake_apply_session_cookie)

    result = asyncio.run(
        usuario.login_usuario(_request_sem_headers(), payload, response)
    )

    assert result["status"] == "sucesso"
    assert result["token"] == "token-login"
    assert result["usuario"]["id"] == "USR-001"
    assert calls["cookie_token"] == "token-login"


def test_logout_revoga_token_do_payload(monkeypatch):
    request = _request_sem_headers()
    response = Response()
    payload = UsuarioLogout(token="token-explicito")
    calls: dict = {"revoked": None, "cookie_cleared": False}

    monkeypatch.setattr(
        usuario, "extract_session_token", lambda req, auth: "token-header"
    )
    monkeypatch.setattr(
        usuario, "revoke_sessao", lambda token: calls.update({"revoked": token}) or True
    )
    monkeypatch.setattr(
        usuario,
        "clear_session_cookie",
        lambda resp: calls.update({"cookie_cleared": True}),
    )

    result = asyncio.run(usuario.logout_usuario(request, response, payload))

    assert result["status"] == "sucesso"
    assert calls["revoked"] == "token-explicito"
    assert calls["cookie_cleared"] is True


def test_logout_sem_token_ainda_limpa_cookie(monkeypatch):
    request = _request_sem_headers()
    response = Response()
    calls: dict = {"revoked_called": False, "cookie_cleared": False}

    monkeypatch.setattr(usuario, "extract_session_token", lambda req, auth: None)

    def fake_revoke(_token):
        calls["revoked_called"] = True
        return True

    monkeypatch.setattr(usuario, "revoke_sessao", fake_revoke)
    monkeypatch.setattr(
        usuario,
        "clear_session_cookie",
        lambda resp: calls.update({"cookie_cleared": True}),
    )

    result = asyncio.run(usuario.logout_usuario(request, response, None))

    assert result["status"] == "sucesso"
    assert calls["revoked_called"] is False
    assert calls["cookie_cleared"] is True


def test_obter_sessao_retorna_usuario_basico():
    result = asyncio.run(
        usuario.obter_sessao(
            usuario={
                "id": "USR-001",
                "nome": "Ana",
                "email": "ana@teste.com",
                "token": "abc",
            }
        )
    )

    assert result["status"] == "sucesso"
    assert result["usuario"]["id"] == "USR-001"
    assert "token" not in result["usuario"]
