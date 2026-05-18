"""Quest 2 — Testa validacao de MIME via magic bytes."""

import base64

import pytest
from pydantic import ValidationError

from App.models.processo import Processo

BASE = {
    "numero_processo": "0001234-56.2026.8.00.0000",
    "autor": "Joao",
    "tipo_acao": "Reclamacao trabalhista",
    "fatos": "Fatos do caso",
    "pedido_autor": "Pagamento de verbas",
    "arquivo_base_nome": "doc.pdf",
}


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode()


# ── Tipos validos ────────────────────────────────────────────────────────────


def test_pdf_valido_aceito():
    conteudo = _b64(b"%PDF-1.4 fake pdf content here")
    p = Processo(**{**BASE, "arquivo_base_conteudo_base64": conteudo})
    assert p.arquivo_base_conteudo_base64 == conteudo


def test_doc_valido_aceito():
    conteudo = _b64(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    p = Processo(
        **{
            **BASE,
            "arquivo_base_nome": "doc.doc",
            "arquivo_base_conteudo_base64": conteudo,
        }
    )
    assert p.arquivo_base_conteudo_base64 is not None


def test_docx_valido_aceito():
    # DOCX = ZIP com magic PK\x03\x04
    conteudo = _b64(b"PK\x03\x04" + b"\x00" * 100)
    p = Processo(
        **{
            **BASE,
            "arquivo_base_nome": "doc.docx",
            "arquivo_base_conteudo_base64": conteudo,
        }
    )
    assert p.arquivo_base_conteudo_base64 is not None


# ── Tipos invalidos (MIME spoofing) ──────────────────────────────────────────


def test_exe_disfarçado_de_pdf_rejeitado():
    """Bytes de executavel Windows (MZ) com extensao .pdf devem ser rejeitados."""
    conteudo = _b64(b"MZ\x90\x00" + b"\x00" * 100)  # PE/EXE magic bytes
    with pytest.raises(ValidationError, match="nao corresponde"):
        Processo(**{**BASE, "arquivo_base_conteudo_base64": conteudo})


def test_texto_com_extensao_pdf_rejeitado():
    """Arquivo de texto puro com extensao .pdf deve ser rejeitado."""
    conteudo = _b64(b"Hello World este e um arquivo de texto simples")
    with pytest.raises(ValidationError, match="nao corresponde"):
        Processo(**{**BASE, "arquivo_base_conteudo_base64": conteudo})


def test_zip_generico_com_extensao_pdf_rejeitado():
    """ZIP que nao e DOCX (magic diferente) com extensao .pdf deve ser rejeitado."""
    # ZIP local file header com versao diferente que nao e OpenXML
    conteudo = _b64(b"PK\x05\x06" + b"\x00" * 18)  # End of central directory
    with pytest.raises(ValidationError, match="nao corresponde"):
        Processo(**{**BASE, "arquivo_base_conteudo_base64": conteudo})


def test_base64_invalido_rejeitado():
    with pytest.raises(ValidationError, match="invalido em base64"):
        Processo(**{**BASE, "arquivo_base_conteudo_base64": "nao_e_base64!!!"})
