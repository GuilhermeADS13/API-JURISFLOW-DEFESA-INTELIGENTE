"""Schemas Pydantic da feature de edicao ciruurgica de contestacao .docx."""

from __future__ import annotations

import base64
import binascii
import os
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from App.models.processo import PROCESSO_REGEX

# .docx eh ZIP/OpenXML — permitimos apenas esse formato porque python-docx so
# manipula .docx, e a feature precisa preservar formatacao.
ALLOWED_EDICAO_EXTENSIONS = (".docx",)
DOCX_MAGIC_BYTES = b"PK\x03\x04"
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Aceita "27.598,41", "1.000,00", "100,00", "R$ 27.598,41".
VALOR_CAUSA_REGEX = re.compile(r"^(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}$")


class EdicaoContestacao(BaseModel):
    """Payload para POST /api/editar-contestacao.

    O usuario envia um .docx base e ate 3 campos novos. Pelo menos um campo
    novo eh obrigatorio. O agente IA decide qual texto antigo substituir;
    o backend aplica a substituicao com python-docx.
    """

    model_config = ConfigDict(extra="ignore")

    arquivo_base_conteudo_base64: Annotated[str, Field(min_length=1)]
    arquivo_base_nome: Annotated[str, Field(min_length=1, max_length=255)]
    arquivo_base_mime_type: str | None = None
    arquivo_base_tamanho_bytes: int | None = None

    nome_novo: str | None = None
    numero_processo_novo: str | None = None
    valor_causa_novo: str | None = None

    @field_validator("arquivo_base_nome")
    @classmethod
    def validar_nome_arquivo(cls, value: str) -> str:
        # Sanitiza path traversal antes de qualquer validacao.
        nome = os.path.basename(value.strip())
        if not nome:
            raise ValueError("Nome de arquivo invalido.")
        if not nome.lower().endswith(ALLOWED_EDICAO_EXTENSIONS):
            raise ValueError("Arquivo base deve ser .docx.")
        return nome

    @field_validator("arquivo_base_conteudo_base64")
    @classmethod
    def validar_arquivo_base64(cls, value: str) -> str:
        conteudo = value.strip()
        if not conteudo:
            raise ValueError("Conteudo do arquivo base obrigatorio.")

        try:
            raw = base64.b64decode(conteudo, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Conteudo do arquivo base invalido em base64.") from error

        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise ValueError("Arquivo base excede o tamanho maximo de 10MB.")

        if not raw.startswith(DOCX_MAGIC_BYTES):
            raise ValueError(
                "Conteudo do arquivo nao corresponde a um .docx valido (assinatura ZIP ausente)."
            )

        return conteudo

    @field_validator("arquivo_base_tamanho_bytes")
    @classmethod
    def validar_tamanho(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("Tamanho do arquivo base invalido.")
        if value > MAX_FILE_SIZE_BYTES:
            raise ValueError("Arquivo base excede o tamanho maximo de 10MB.")
        return value

    @field_validator("nome_novo")
    @classmethod
    def validar_nome_novo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        nome = value.strip()
        if not nome:
            return None
        if len(nome) < 3:
            raise ValueError("nome_novo deve ter ao menos 3 caracteres.")
        if len(nome) > 200:
            raise ValueError("nome_novo deve ter no maximo 200 caracteres.")
        return nome

    @field_validator("numero_processo_novo")
    @classmethod
    def validar_numero_processo_novo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        numero = value.strip()
        if not numero:
            return None
        if not PROCESSO_REGEX.fullmatch(numero):
            raise ValueError(
                "numero_processo_novo no formato CNJ esperado: 0001234-56.2026.8.00.0000."
            )
        return numero

    @field_validator("valor_causa_novo")
    @classmethod
    def validar_valor_causa_novo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        valor = value.strip()
        if not valor:
            return None
        if not VALOR_CAUSA_REGEX.fullmatch(valor):
            raise ValueError(
                "valor_causa_novo no formato monetario esperado: 27.598,41 ou R$ 27.598,41."
            )
        return valor

    @model_validator(mode="after")
    def pelo_menos_um_campo_novo(self):
        if not (self.nome_novo or self.numero_processo_novo or self.valor_causa_novo):
            raise ValueError(
                "Informe ao menos um campo a substituir (nome_novo, numero_processo_novo ou valor_causa_novo)."
            )
        return self


class SubstituicaoIA(BaseModel):
    """Item da resposta do agente IA: par antigo<->novo identificado no .docx."""

    model_config = ConfigDict(extra="ignore")

    campo: Annotated[str, Field(min_length=1)]
    antigo: Annotated[str, Field(min_length=1)]
    novo: Annotated[str, Field(min_length=1)]
    ocorrencias_esperadas: Annotated[int, Field(ge=1)]


class RespostaAgenteEdicao(BaseModel):
    """Resposta do workflow n8n editar-contestacao para o backend.

    Backend valida ocorrencias_esperadas contra o que realmente existe no .docx
    antes de aplicar a substituicao (impede troca de ocorrencia errada).
    """

    model_config = ConfigDict(extra="ignore")

    substituicoes: list[SubstituicaoIA] = []
    campos_ausentes: list[str] = []
