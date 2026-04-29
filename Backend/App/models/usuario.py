"""Schemas Pydantic relacionados ao ciclo de usuario/autenticacao."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Regex de e-mail mais restritiva: nao aceita TLD de 1 caractere, varios @,
# nem caracteres de controle. NAO substitui RFC 5322 completo, mas filtra a
# maior parte dos invalidos sem precisar de dependencia externa.
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*\.[A-Za-z]{2,24}$"
)


def normalizar_email(email: str) -> str:
    """Remove espacos e padroniza e-mail em minusculas."""
    return email.strip().lower()


def senha_forte(senha: str) -> bool:
    """Aplica politica de senha forte usada no backend."""
    if any(char.isspace() for char in senha):
        return False
    if not any(char.isupper() for char in senha):
        return False
    if not any(char.islower() for char in senha):
        return False
    if not any(char.isdigit() for char in senha):
        return False
    if not any(not char.isalnum() for char in senha):
        return False
    return True


class Usuario(BaseModel):
    """Modelo completo de usuario (inclui id e senha)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Annotated[str, Field(min_length=1, max_length=64)]
    nome: Annotated[str, Field(min_length=3, max_length=120, alias="name")]
    email: Annotated[str, Field(min_length=6, max_length=254)]
    senha: Annotated[str, Field(min_length=8, max_length=128, alias="password")]

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, value: str) -> str:
        nome = value.strip()
        if len(nome) < 3:
            raise ValueError("Informe um nome valido com ao menos 3 caracteres.")
        return nome

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str) -> str:
        email = normalizar_email(value)
        if not EMAIL_REGEX.fullmatch(email):
            raise ValueError("Informe um e-mail valido.")
        return email

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, value: str) -> str:
        senha = value.strip()
        if not senha_forte(senha):
            raise ValueError(
                "A senha deve ter pelo menos 8 caracteres, com maiuscula, minuscula, numero e simbolo."
            )
        return senha

    @field_validator("id")
    @classmethod
    def validar_id(cls, value: str) -> str:
        identifier = value.strip()
        if not identifier:
            raise ValueError("Informe um id valido.")
        return identifier


class UsuarioCadastro(BaseModel):
    """Payload aceito no endpoint de criacao de conta."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    nome: Annotated[str, Field(min_length=3, max_length=120, alias="name")]
    email: Annotated[str, Field(min_length=6, max_length=254)]
    senha: Annotated[str, Field(min_length=8, max_length=128, alias="password")]

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, value: str) -> str:
        nome = value.strip()
        if len(nome) < 3:
            raise ValueError("Informe um nome valido com ao menos 3 caracteres.")
        return nome

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str) -> str:
        email = normalizar_email(value)
        if not EMAIL_REGEX.fullmatch(email):
            raise ValueError("Informe um e-mail valido.")
        return email

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, value: str) -> str:
        senha = value.strip()
        if not senha_forte(senha):
            raise ValueError(
                "A senha deve ter pelo menos 8 caracteres, com maiuscula, minuscula, numero e simbolo."
            )
        return senha


class UsuarioLogin(BaseModel):
    """Payload aceito no endpoint de login."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    email: Annotated[str, Field(min_length=6, max_length=254)]
    senha: Annotated[str, Field(min_length=1, max_length=128, alias="password")]

    @field_validator("email")
    @classmethod
    def validar_email(cls, value: str) -> str:
        email = normalizar_email(value)
        if not EMAIL_REGEX.fullmatch(email):
            raise ValueError("Informe um e-mail valido.")
        return email

    @field_validator("senha")
    @classmethod
    def validar_senha_login(cls, value: str) -> str:
        senha = value.strip()
        if not senha:
            raise ValueError("Informe a senha.")
        return senha


class UsuarioLogout(BaseModel):
    """Payload opcional para logout (cookie e usado como fallback principal)."""

    token: str | None = Field(default=None, min_length=8, max_length=256)

    @field_validator("token")
    @classmethod
    def validar_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip()
        if not token:
            raise ValueError("Token de sessao invalido.")
        return token
