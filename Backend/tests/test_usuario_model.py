"""Testes de validacao dos schemas e utilitarios de usuario."""

import pytest
from pydantic import ValidationError

from App.models.usuario import (
    UsuarioCadastro,
    UsuarioLogin,
    UsuarioLogout,
    normalizar_email,
    senha_forte,
)


def test_normalizar_email_remove_espacos_e_minusculas():
    assert normalizar_email("  USUARIO@Email.COM  ") == "usuario@email.com"


@pytest.mark.parametrize(
    "senha,esperado",
    [
        ("Senha@123", True),
        ("senha@123", False),
        ("SENHA@123", False),
        ("SenhaSemNumero@", False),
        ("Senha123", False),
        ("Senha @123", False),
    ],
)
def test_senha_forte_regras_minimas(senha, esperado):
    assert senha_forte(senha) is esperado


def test_usuario_cadastro_valido():
    model = UsuarioCadastro(
        name="Ana Silva", email="ana@teste.com", password="Senha@123"
    )
    assert model.nome == "Ana Silva"
    assert model.email == "ana@teste.com"


@pytest.mark.parametrize("email", ["", "ana", "ana@invalido", "ana.com"])
def test_usuario_cadastro_rejeita_email_invalido(email):
    with pytest.raises(ValidationError):
        UsuarioCadastro(name="Ana Silva", email=email, password="Senha@123")


@pytest.mark.parametrize("senha", ["123", "senhafraca", "SenhaSemNumero@", "SENHA@123"])
def test_usuario_cadastro_rejeita_senha_fraca(senha):
    with pytest.raises(ValidationError):
        UsuarioCadastro(name="Ana Silva", email="ana@teste.com", password=senha)


def test_usuario_login_valido():
    model = UsuarioLogin(email="ana@teste.com", password="Senha@123")
    assert model.email == "ana@teste.com"


def test_usuario_logout_aceita_token_opcional():
    sem_token = UsuarioLogout()
    com_token = UsuarioLogout(token="abc123def456")
    assert sem_token.token is None
    assert com_token.token == "abc123def456"
