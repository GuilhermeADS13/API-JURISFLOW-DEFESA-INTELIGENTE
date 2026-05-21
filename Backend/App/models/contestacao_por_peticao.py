"""Schema Pydantic da entrada de contestacao gerada a partir da peticao inicial.

O usuario faz upload da peticao inicial (PDF ou DOCX). O sistema extrai dados
estruturados via Claude e gera a contestacao automaticamente. Modelo base do
escritorio (DOCX com placeholders Jinja2) e opcional.

PR5 (Guia Tecnico v3) adiciona:
- ArquivoAnexo: anexos opcionais consolidados ao texto da peticao.
- ContestacaoPorPeticao.arquivos_anexos: lista (max 5) de anexos.
- ConfirmacaoExtracao: payload do POST /confirmar-extracao quando a IA teve
  baixa confianca e o advogado precisou revisar/corrigir os dados extraidos.
"""

from __future__ import annotations

import base64
import binascii
import os
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_PETICAO_EXTENSIONS = (".pdf", ".docx", ".doc")
ALLOWED_MODELO_BASE_EXTENSIONS = (".docx",)
ALLOWED_ANEXO_EXTENSIONS = (".pdf", ".docx", ".doc")
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB — peticoes podem ser grandes
MAX_ANEXOS = 5
MAX_TOTAL_ANEXOS_BYTES = 50 * 1024 * 1024  # 50MB somando todos os anexos

# Magic bytes dos formatos permitidos. PDF: %PDF, DOC: OLE2 compound, DOCX: ZIP.
_MAGIC_BYTES_PETICAO: list[bytes] = [
    b"%PDF",
    b"\xd0\xcf\x11\xe0",
    b"PK\x03\x04",
]
_MAGIC_BYTES_DOCX = b"PK\x03\x04"


class ArquivoAnexo(BaseModel):
    """Anexo opcional juntado a peticao inicial (contratos, e-mails, laudos).

    Backend extrai texto e concatena com a peticao antes de enviar a IA.
    """

    model_config = ConfigDict(extra="ignore")

    base64: Annotated[str, Field(min_length=1)]
    nome: Annotated[str, Field(min_length=1, max_length=255)]
    mime_type: str = "application/octet-stream"

    @field_validator("nome")
    @classmethod
    def validar_nome_anexo(cls, value: str) -> str:
        nome = os.path.basename(value.strip())
        if not nome:
            raise ValueError("Nome de anexo invalido.")
        if not nome.lower().endswith(ALLOWED_ANEXO_EXTENSIONS):
            raise ValueError("Anexo deve ser PDF, DOC ou DOCX.")
        return nome

    @field_validator("base64")
    @classmethod
    def validar_conteudo_anexo(cls, value: str) -> str:
        conteudo = value.strip()
        if not conteudo:
            raise ValueError("Conteudo do anexo obrigatorio.")
        try:
            raw = base64.b64decode(conteudo, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Conteudo do anexo invalido em base64.") from error
        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise ValueError("Anexo excede 20MB.")
        if not any(raw.startswith(m) for m in _MAGIC_BYTES_PETICAO):
            raise ValueError(
                "Conteudo do anexo nao corresponde a PDF, DOC ou DOCX valido."
            )
        return conteudo


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

    # PR5 - Multi-documentos
    arquivos_anexos: list[ArquivoAnexo] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_anexos_agregados(self):
        if len(self.arquivos_anexos) > MAX_ANEXOS:
            raise ValueError(f"Maximo de {MAX_ANEXOS} anexos por peticao.")
        total = 0
        for a in self.arquivos_anexos:
            try:
                total += len(base64.b64decode(a.base64.strip(), validate=True))
            except (binascii.Error, ValueError):
                # base64 malformado neste anexo: ignora no calculo do total;
                # a validacao pontual de cada anexo acontece em ArquivoAnexo.
                continue
        if total > MAX_TOTAL_ANEXOS_BYTES:
            raise ValueError(
                f"Soma dos anexos excede {MAX_TOTAL_ANEXOS_BYTES // 1024 // 1024}MB."
            )
        return self

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
            raise ValueError(
                "Modelo base deve ser um .docx valido (assinatura ZIP ausente)."
            )
        return conteudo

    @field_validator("tipo_acao_hint", "pontos_contestante")
    @classmethod
    def normalizar_texto_opcional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        texto = value.strip()
        return texto or None


class ConfirmacaoExtracao(BaseModel):
    """Payload do POST /api/contestacoes/{id}/confirmar-extracao (PR5 HiL).

    Quando a IA teve baixa confianca, o advogado revisa os dados extraidos
    e envia a versao corrigida. O backend pula o Claude Extrator e vai
    direto para o RAG + Gerador com `dados_extraidos_pre_validados`.
    """

    model_config = ConfigDict(extra="ignore")

    dados_extraidos: dict[str, Any] = Field(default_factory=dict)
    pontos_contestante: str | None = None
    modelo_base_base64: str | None = None
    modelo_base_nome: str | None = None

    @field_validator("dados_extraidos")
    @classmethod
    def validar_dados_extraidos(cls, value: dict) -> dict:
        # Campos minimos que o agente Claude Gerador espera para nao alucinar.
        if not value.get("autor"):
            raise ValueError("dados_extraidos.autor obrigatorio.")
        if not value.get("tipo_acao"):
            raise ValueError("dados_extraidos.tipo_acao obrigatorio.")
        # Garante shape de listas para nao quebrar o gerador.
        if "pedidos" not in value:
            value["pedidos"] = []
        if not isinstance(value.get("pedidos"), list):
            value["pedidos"] = [str(value["pedidos"])]
        return value

    @field_validator("pontos_contestante")
    @classmethod
    def normalizar_pontos(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip()
        return v or None


class MinutaEditada(BaseModel):
    """Payload do PATCH /api/contestacoes/{id}/minuta (PR5 Observabilidade).

    Capturamos as edicoes do advogado para futuro fine-tuning + metricas
    de qualidade da IA. Todos os campos sao opcionais — apenas os enviados
    sao gravados em `minuta_json_editada`.
    """

    model_config = ConfigDict(extra="ignore")

    tese_central: str | None = None
    preliminares: str | None = None
    merito: str | None = None
    fundamentos: str | None = None
    pedidos: str | None = None
    observacoes: str | None = None
    impugnacao_pedidos: dict[str, str] | None = None

    @model_validator(mode="after")
    def pelo_menos_um_campo(self):
        campos = [
            self.tese_central,
            self.preliminares,
            self.merito,
            self.fundamentos,
            self.pedidos,
            self.observacoes,
            self.impugnacao_pedidos,
        ]
        if not any(c is not None and c != "" for c in campos):
            raise ValueError("Informe ao menos um campo da minuta para editar.")
        return self
