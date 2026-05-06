"""Schema Pydantic da entrada de contestacao gerada a partir da peticao inicial.

O usuario faz upload da peticao inicial (PDF ou DOCX). O sistema extrai dados
estruturados via Claude e gera a contestacao automaticamente. Modelo base do
escritorio (DOCX com placeholders Jinja2) e opcional.
"""

from __future__ import annotations

import base64
import binascii
import os
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_PETICAO_EXTENSIONS = (".pdf", ".docx", ".doc")
ALLOWED_MODELO_BASE_EXTENSIONS = (".docx",)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB — peticoes podem ser grandes

# Magic bytes dos formatos permitidos. PDF: %PDF, DOC: OLE2 compound, DOCX: ZIP.
_MAGIC_BYTES_PETICAO: list[bytes] = [
    b"%PDF",
    b"\xd0\xcf\x11\xe0",
    b"PK\x03\x04",
]
_MAGIC_BYTES_DOCX = b"PK\x03\x04"


class ContestacaoPorPeticao(BaseModel):
    """Payload para POST /api/contestar-por-peticao.

    Recebe a peticao inicial (obrigatoria) e, opcionalmente, um modelo base
    .docx do escritorio com placeholders Jinja2 do tipo {{ campo }} para
    preenchimento automatico via docxtpl.
    """

    model_config = ConfigDict(extra="ignore")

    arquivo_peticao_base64: Annotated[str, Field(min_length=1)]
    arquivo_peticao_nome: Annotated[str, Field(min_length=1, max_length=255)]
    arquivo_peticao_mime_type: str = "application/octet-stream"

    modelo_base_base64: str | None = None
    modelo_base_nome: str | None = None

    tipo_acao_hint: str | None = None
    pontos_contestante: str | None = None

    @field_validator("arquivo_peticao_nome")
    @classmethod
    def validar_nome_peticao(cls, value: str) -> str:
        nome = os.path.basename(value.strip())
        if not nome:
            raise ValueError("Nome de arquivo invalido.")
        if not nome.lower().endswith(ALLOWED_PETICAO_EXTENSIONS):
            raise ValueError("Peticao deve ser PDF, DOC ou DOCX.")
        return nome

    @field_validator("modelo_base_nome")
    @classmethod
    def validar_nome_modelo_base(cls, value: str | None) -> str | None:
        if value is None:
            return None
        nome = os.path.basename(value.strip())
        if not nome:
            return None
        if not nome.lower().endswith(ALLOWED_MODELO_BASE_EXTENSIONS):
            raise ValueError("Modelo base deve ser .docx.")
        return nome

    @field_validator("arquivo_peticao_base64")
    @classmethod
    def validar_arquivo_peticao(cls, value: str) -> str:
        conteudo = value.strip()
        if not conteudo:
            raise ValueError("Conteudo da peticao obrigatorio.")
        try:
            raw = base64.b64decode(conteudo, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Conteudo da peticao invalido em base64.") from error
        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise ValueError("Peticao excede o tamanho maximo de 20MB.")
        if not any(raw.startswith(magic) for magic in _MAGIC_BYTES_PETICAO):
            raise ValueError(
                "Conteudo da peticao nao corresponde a um PDF, DOC ou DOCX valido."
            )
        return conteudo

    @field_validator("modelo_base_base64")
    @classmethod
    def validar_modelo_base(cls, value: str | None) -> str | None:
        if value is None:
            return None
        conteudo = value.strip()
        if not conteudo:
            return None
        try:
            raw = base64.b64decode(conteudo, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Modelo base invalido em base64.") from error
        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise ValueError("Modelo base excede o tamanho maximo de 20MB.")
        if not raw.startswith(_MAGIC_BYTES_DOCX):
            raise ValueError("Modelo base deve ser um .docx valido (assinatura ZIP ausente).")
        return conteudo

    @field_validator("tipo_acao_hint", "pontos_contestante")
    @classmethod
    def normalizar_texto_opcional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        texto = value.strip()
        return texto or None
