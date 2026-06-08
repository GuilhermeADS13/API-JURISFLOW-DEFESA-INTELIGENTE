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
# PR15: extensoes aceitas pra embedding visual (imagens + PDFs convertidos).
ALLOWED_EMBED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".pdf")
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB — peticoes podem ser grandes
MAX_ANEXOS = 5
MAX_TOTAL_ANEXOS_BYTES = 50 * 1024 * 1024  # 50MB somando todos os anexos
# PR15: provas embedaveis no docx final (imagens FGTS/TRCT/laudos/prints).
MAX_ARQUIVOS_EMBEDAR = 10
MAX_TOTAL_EMBED_BYTES = 30 * 1024 * 1024  # 30MB somando todos
MAX_EMBED_FILE_BYTES = 10 * 1024 * 1024  # 10MB por arquivo embedavel

# Tipos canonicos pra casar com documentos_anexos[].tipo gerado pelo Claude.
# Sao os mesmos slugs usados no enum do frontend e no mapeamento do builder.
TIPOS_EMBED_CANONICOS = frozenset({
    "folha_ponto",
    "fgts",
    "trct",
    "laudo_pericial",
    "contrato",
    "ctps",
    "print",
    "outro",
})

# Magic bytes dos formatos permitidos. PDF: %PDF, DOC: OLE2 compound, DOCX: ZIP.
_MAGIC_BYTES_PETICAO: list[bytes] = [
    b"%PDF",
    b"\xd0\xcf\x11\xe0",
    b"PK\x03\x04",
]
_MAGIC_BYTES_DOCX = b"PK\x03\x04"
# PR15: magic bytes pra imagens.
_MAGIC_BYTES_JPG = (b"\xff\xd8\xff",)  # JPEG (SOI marker)
_MAGIC_BYTES_PNG = (b"\x89PNG\r\n\x1a\n",)
_MAGIC_BYTES_PDF = (b"%PDF",)


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


class ArquivoEmbedar(BaseModel):
    """PR15: prova a embedar VISUALMENTE no docx final (imagem/PDF).

    Diferente de ArquivoAnexo (que vai pra extracao de texto/OCR), este
    aqui eh inserido como imagem no proprio docx via doc.add_picture() —
    apos o item correspondente em documentos_anexos[] gerado pelo Claude.

    `tipo` casa com a taxonomia em TIPOS_EMBED_CANONICOS — usado pra mapear
    com o item certo da lista que o Claude gerou (folha_ponto -> Doc. 03, etc).
    """

    model_config = ConfigDict(extra="ignore")

    base64: Annotated[str, Field(min_length=1)]
    nome: Annotated[str, Field(min_length=1, max_length=255)]
    mime_type: str = "application/octet-stream"
    tipo: Annotated[str, Field(min_length=1, max_length=40)]

    @field_validator("nome")
    @classmethod
    def validar_nome_embed(cls, value: str) -> str:
        nome = os.path.basename(value.strip())
        if not nome:
            raise ValueError("Nome de arquivo embedavel invalido.")
        if not nome.lower().endswith(ALLOWED_EMBED_EXTENSIONS):
            raise ValueError(
                "Arquivo embedavel deve ser JPG, JPEG, PNG ou PDF."
            )
        return nome

    @field_validator("tipo")
    @classmethod
    def validar_tipo_embed(cls, value: str) -> str:
        tipo_norm = (value or "").strip().lower()
        if tipo_norm not in TIPOS_EMBED_CANONICOS:
            raise ValueError(
                f"tipo invalido: {tipo_norm!r}. Use um de: "
                + ", ".join(sorted(TIPOS_EMBED_CANONICOS))
            )
        return tipo_norm

    @field_validator("base64")
    @classmethod
    def validar_conteudo_embed(cls, value: str) -> str:
        conteudo = value.strip()
        if not conteudo:
            raise ValueError("Conteudo do arquivo embedavel obrigatorio.")
        try:
            raw = base64.b64decode(conteudo, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Conteudo embedavel invalido em base64.") from error
        if len(raw) > MAX_EMBED_FILE_BYTES:
            raise ValueError(
                f"Arquivo embedavel excede {MAX_EMBED_FILE_BYTES // 1024 // 1024}MB."
            )
        magic_validos = _MAGIC_BYTES_JPG + _MAGIC_BYTES_PNG + _MAGIC_BYTES_PDF
        if not any(raw.startswith(m) for m in magic_validos):
            raise ValueError(
                "Conteudo embedavel nao corresponde a JPG, PNG ou PDF valido."
            )
        return conteudo


class ContestacaoPorPeticao(BaseModel):
    """Payload para POST /api/contestar-por-peticao.

    Recebe a peticao inicial (obrigatoria) e, opcionalmente, um modelo base
    .docx do escritorio com placeholders do tipo {{ campo }} para
    preenchimento automatico via python-docx.
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

    # PR15: provas embedaveis visualmente no docx final (max 10).
    arquivos_embedar: list[ArquivoEmbedar] = Field(default_factory=list)

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

        # PR15: valida limite e tamanho dos arquivos embedaveis.
        if len(self.arquivos_embedar) > MAX_ARQUIVOS_EMBEDAR:
            raise ValueError(
                f"Maximo de {MAX_ARQUIVOS_EMBEDAR} arquivos embedaveis por peticao."
            )
        total_embed = 0
        for e in self.arquivos_embedar:
            try:
                total_embed += len(base64.b64decode(e.base64.strip(), validate=True))
            except (binascii.Error, ValueError):
                continue
        if total_embed > MAX_TOTAL_EMBED_BYTES:
            raise ValueError(
                f"Soma dos arquivos embedaveis excede {MAX_TOTAL_EMBED_BYTES // 1024 // 1024}MB."
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
