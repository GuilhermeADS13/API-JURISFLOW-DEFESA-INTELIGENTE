"""Schema Pydantic da entrada de suporte/contato."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from App.models.processo import PROCESSO_REGEX
from App.models.usuario import EMAIL_REGEX, normalizar_email


class SuporteContato(BaseModel):
    """Payload aceito para envio de reclamacao ao suporte."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    nome: Annotated[str, Field(min_length=3, max_length=120, alias="name")]
    email: Annotated[str, Field(min_length=6, max_length=254)]
    categoria: Annotated[str, Field(min_length=3, max_length=120, alias="category")]
    numero_processo: Annotated[str | None, Field(default=None, alias="processo")] = None
    assunto: Annotated[str, Field(min_length=4, max_length=160, alias="subject")]
    mensagem: Annotated[str, Field(min_length=15, max_length=4000, alias="message")]

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

    @field_validator("categoria")
    @classmethod
    def validar_categoria(cls, value: str) -> str:
        categoria = value.strip()
        if len(categoria) < 3:
            raise ValueError("Informe a categoria da reclamacao.")
        return categoria

    @field_validator("numero_processo")
    @classmethod
    def validar_numero_processo(cls, value: str | None) -> str | None:
        if value is None:
            return None

        numero = value.strip()
        if not numero:
            return None
        if not PROCESSO_REGEX.fullmatch(numero):
            raise ValueError("Use o formato 0001234-56.2026.8.00.0000.")
        return numero

    @field_validator("assunto")
    @classmethod
    def validar_assunto(cls, value: str) -> str:
        assunto = value.strip()
        if len(assunto) < 4:
            raise ValueError("Informe um assunto valido.")
        return assunto

    @field_validator("mensagem")
    @classmethod
    def validar_mensagem(cls, value: str) -> str:
        mensagem = value.strip()
        if len(mensagem) < 15:
            raise ValueError("Detalhe mais a reclamacao (minimo de 15 caracteres).")
        return mensagem
