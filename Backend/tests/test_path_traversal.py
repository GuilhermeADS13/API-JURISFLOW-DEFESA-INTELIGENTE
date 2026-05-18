"""Quest 2 — Testa sanitizacao de path traversal em nomes de arquivo."""

import pytest
from pydantic import ValidationError

from App.models.processo import Processo

BASE = {
    "numero_processo": "0001234-56.2026.8.00.0000",
    "autor": "Joao",
    "tipo_acao": "Reclamacao trabalhista",
    "fatos": "Fatos do caso",
    "pedido_autor": "Pagamento de verbas",
}

# PDF minimo valido em base64 (magic bytes %PDF + estrutura minima)
PDF_B64 = "JVBE"  # %PDF — apenas os 4 bytes de magic para o teste de nome


def _make(nome, b64="JVBE"):
    # Gera base64 valido com magic bytes de PDF para passar na validacao de conteudo
    import base64

    conteudo = base64.b64encode(b"%PDF-1.4 fake content").decode()
    return {**BASE, "arquivo_base_nome": nome, "arquivo_base_conteudo_base64": conteudo}


def test_path_traversal_unix():
    """../../etc/passwd.pdf deve virar passwd.pdf."""
    p = Processo(**_make("../../etc/passwd.pdf"))
    assert p.arquivo_base_nome == "passwd.pdf"
    assert p.arquivo_base == "passwd.pdf"


def test_path_traversal_windows():
    """..\\..\\windows\\system32\\calc.pdf deve virar calc.pdf."""
    p = Processo(**_make("..\\..\\windows\\system32\\calc.pdf"))
    assert p.arquivo_base_nome == "calc.pdf"


def test_path_traversal_encoded():
    """%2e%2e%2fetc%2fpasswd.pdf — os.path.basename trata como string literal."""
    p = Processo(**_make("%2e%2e%2fetc%2fpasswd.pdf"))
    assert "/" not in p.arquivo_base_nome


def test_nome_vazio_apos_basename():
    """Nome que resulta em string vazia apos basename deve ser rejeitado."""
    with pytest.raises(ValidationError, match="invalido"):
        Processo(**_make("/"))


def test_nome_normal_preservado():
    """Nome sem path deve ser preservado intacto."""
    p = Processo(**_make("peticao_inicial.pdf"))
    assert p.arquivo_base_nome == "peticao_inicial.pdf"
