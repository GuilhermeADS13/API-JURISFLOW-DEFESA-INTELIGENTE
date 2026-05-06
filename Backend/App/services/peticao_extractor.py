"""Extrator de texto de peticao inicial em PDF ou DOCX.

Usado pela rota POST /api/contestar-por-peticao antes de enviar o conteudo ao
agente IA. Mantem a logica de extracao no backend (nao no n8n) porque o
container n8n base nao tem mammoth/pdfjs-dist, e Python ja tem libs maduras.
"""

from __future__ import annotations

import base64
import binascii
from io import BytesIO

from docx import Document
from pypdf import PdfReader

# Limite de caracteres entregues ao prompt do extrator. Peticoes grandes podem
# ultrapassar facilmente o context window util do Claude — cortamos antes de
# enviar para evitar custo e latencia desnecessarios.
MAX_TEXTO_PETICAO_CHARS = 20_000
MAX_TEXTO_MODELO_BASE_CHARS = 15_000


class ExtracaoError(Exception):
    """Falha ao extrair texto do arquivo enviado."""


def extrair_texto_peticao(conteudo: bytes, nome: str) -> str:
    """Extrai texto da peticao inicial. Detecta tipo pela extensao do nome.

    Limita a saida a `MAX_TEXTO_PETICAO_CHARS` chars. Levanta `ExtracaoError`
    se o conteudo estiver corrompido ou se nao for possivel obter texto util
    (>=50 chars apos strip).
    """
    if not conteudo:
        raise ExtracaoError("Conteudo da peticao vazio.")

    nome_lower = (nome or "").lower().strip()

    if nome_lower.endswith(".docx"):
        texto = _extrair_docx(conteudo)
    elif nome_lower.endswith(".pdf"):
        texto = _extrair_pdf(conteudo)
    elif nome_lower.endswith(".doc"):
        # .doc legado — extracao basica de texto legivel ASCII/Latin-1.
        texto = conteudo.decode("latin1", errors="ignore")
        # Remove caracteres de controle nao-imprimiveis exceto quebras de linha.
        texto = "".join(c for c in texto if c == "\n" or c == "\r" or c == "\t" or 0x20 <= ord(c) <= 0xFFFF)
    else:
        raise ExtracaoError(f"Extensao nao suportada para extracao: {nome!r}")

    # Normaliza whitespace e limita tamanho.
    texto = _limpar_texto(texto)[:MAX_TEXTO_PETICAO_CHARS]

    if len(texto.strip()) < 50:
        raise ExtracaoError(
            "Nao foi possivel extrair texto legivel da peticao. "
            "Tente converter para DOCX e enviar novamente."
        )

    return texto


def extrair_texto_modelo_base(conteudo_b64: str | None) -> str:
    """Extrai texto do modelo base .docx (opcional).

    Retorna string vazia em ausencia/erro — o modelo base e opcional e nao deve
    bloquear o fluxo da geracao.
    """
    if not conteudo_b64:
        return ""

    try:
        conteudo = base64.b64decode(conteudo_b64.strip(), validate=True)
    except (binascii.Error, ValueError):
        return ""

    try:
        texto = _extrair_docx(conteudo)
    except ExtracaoError:
        return ""

    return _limpar_texto(texto)[:MAX_TEXTO_MODELO_BASE_CHARS]


def _extrair_docx(conteudo: bytes) -> str:
    try:
        doc = Document(BytesIO(conteudo))
    except Exception as error:
        raise ExtracaoError(
            f"Falha ao abrir o .docx: {type(error).__name__}: {error}"
        ) from error

    linhas: list[str] = []
    for paragraph in doc.paragraphs:
        if paragraph.text:
            linhas.append(paragraph.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if paragraph.text:
                        linhas.append(paragraph.text)

    return "\n".join(linhas)


def _extrair_pdf(conteudo: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(conteudo))
    except Exception as error:
        raise ExtracaoError(
            f"Falha ao abrir o PDF: {type(error).__name__}: {error}"
        ) from error

    paginas: list[str] = []
    # Limita a 30 paginas para evitar PDFs gigantes esgotarem memoria/tempo.
    for page in reader.pages[:30]:
        try:
            paginas.append(page.extract_text() or "")
        except Exception:
            paginas.append("")

    return "\n\n".join(p for p in paginas if p.strip())


def _limpar_texto(texto: str) -> str:
    """Remove sequencias de espacos/quebras redundantes."""
    if not texto:
        return ""
    # Colapsa 3+ quebras consecutivas em 1 para reduzir tokens sem perder estrutura.
    linhas = [linha.rstrip() for linha in texto.splitlines()]
    return "\n".join(linha for linha in linhas if linha != "" or True).strip()
