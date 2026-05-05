# Schema Pydantic da entrada de processo/contestacao e validacoes de arquivo.
import base64
import binascii
import os
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Regex oficial de numero CNJ no formato 0001234-56.2026.8.00.0000.
PROCESSO_REGEX = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
ALLOWED_BASE_FILE_EXTENSIONS = (".pdf", ".doc", ".docx")
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Magic bytes dos formatos permitidos para deteccao de MIME real (sem lib externa).
_MAGIC_BYTES: list[bytes] = [
    b"%PDF",           # PDF
    b"\xd0\xcf\x11\xe0",  # DOC (OLE2 Compound)
    b"PK\x03\x04",    # DOCX (ZIP/OpenXML)
]


class Processo(BaseModel):
    """Modelo de entrada para o fluxo de geracao de contestacao."""

    model_config = ConfigDict(extra="ignore")

    # Campos principais do caso juridico.
    numero_processo: str = Field(..., min_length=1)
    autor: str = Field(..., min_length=1)
    reu: str = Field(default="Nao informado")
    tipo_acao: str = Field(..., min_length=1)
    fatos: str = Field(..., min_length=1)
    pedido_autor: str = Field(..., min_length=1)

    # Campos de arquivo base (nome + conteudo em base64).
    arquivo_base: str | None = None
    arquivo_base_nome: str | None = None
    arquivo_base_conteudo_base64: str | None = None
    arquivo_base_mime_type: str | None = None
    arquivo_base_tamanho_bytes: int | None = None

    # Campo opcional para edicao humana da minuta.
    texto_editado_ao_vivo: str | None = None

    @field_validator("numero_processo")
    @classmethod
    def validar_numero_processo(cls, value: str) -> str:
        numero = value.strip()
        if not PROCESSO_REGEX.fullmatch(numero):
            raise ValueError("Use o formato 0001234-56.2026.8.00.0000.")
        return numero

    @field_validator("autor", "reu", "tipo_acao", "fatos", "pedido_autor")
    @classmethod
    def limpar_texto(cls, value: str) -> str:
        texto = value.strip()
        if not texto:
            raise ValueError("Campo obrigatorio.")
        return texto

    @field_validator("arquivo_base", "arquivo_base_nome")
    @classmethod
    def validar_nome_arquivo(cls, value: str | None) -> str | None:
        if value is None:
            return None

        # Sanitiza path traversal antes de qualquer outra validacao.
        arquivo = os.path.basename(value.strip())
        if not arquivo:
            raise ValueError("Nome de arquivo invalido.")

        if not arquivo.lower().endswith(ALLOWED_BASE_FILE_EXTENSIONS):
            raise ValueError("Arquivo base deve ser DOC, DOCX ou PDF.")
        return arquivo

    @field_validator("arquivo_base_conteudo_base64")
    @classmethod
    def validar_arquivo_base64(cls, value: str | None) -> str | None:
        if value is None:
            return None

        conteudo = value.strip()
        if not conteudo:
            return None

        try:
            raw = base64.b64decode(conteudo, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Conteudo do arquivo base invalido em base64.") from error

        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise ValueError("Arquivo base excede o tamanho maximo de 10MB.")

        # Verifica magic bytes para garantir que o conteudo corresponde ao tipo declarado.
        if not any(raw.startswith(magic) for magic in _MAGIC_BYTES):
            raise ValueError(
                "Conteudo do arquivo nao corresponde a um PDF, DOC ou DOCX valido."
            )

        return conteudo

    @field_validator("arquivo_base_tamanho_bytes")
    @classmethod
    def validar_tamanho_informado(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("Tamanho do arquivo base invalido.")
        if value > MAX_FILE_SIZE_BYTES:
            raise ValueError("Arquivo base excede o tamanho maximo de 10MB.")
        return value

    @field_validator("texto_editado_ao_vivo")
    @classmethod
    def normalizar_texto_editado(cls, value: str | None) -> str | None:
        if value is None:
            return None

        texto = value.strip()
        if not texto:
            return None
        return texto

    @model_validator(mode="after")
    def validar_consistencia_arquivo(self):
        """Mantem consistencia entre nome, conteudo e tamanho do arquivo."""
        nome = (self.arquivo_base_nome or self.arquivo_base or "").strip()
        conteudo = (self.arquivo_base_conteudo_base64 or "").strip()

        if nome and not conteudo:
            raise ValueError("Envie o conteudo base64 do arquivo base junto com o nome.")
        if conteudo and not nome:
            raise ValueError("Informe o nome do arquivo base quando houver conteudo.")

        if nome:
            self.arquivo_base = nome
            self.arquivo_base_nome = nome

        return self
