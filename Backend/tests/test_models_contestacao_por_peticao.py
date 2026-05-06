"""Testes do schema Pydantic ContestacaoPorPeticao (Guia Tecnico v2 - PR1)."""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from docx import Document
from pydantic import ValidationError

from App.models.contestacao_por_peticao import (
    MAX_FILE_SIZE_BYTES,
    ContestacaoPorPeticao,
)


def _pdf_bytes_minimo() -> bytes:
    """Bytes minimos com header %PDF para passar magic bytes."""
    return b"%PDF-1.4\n%\xc3\xa4\xc3\xb6\n" + b"0" * 200


def _docx_bytes_minimo() -> bytes:
    """Constroi um .docx valido (ZIP/OpenXML) usando python-docx."""
    doc = Document()
    doc.add_paragraph("Peticao inicial de teste.")
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _payload(**overrides) -> dict:
    base = {
        "arquivo_peticao_base64": base64.b64encode(_pdf_bytes_minimo()).decode("ascii"),
        "arquivo_peticao_nome": "peticao.pdf",
    }
    base.update(overrides)
    return base


def test_payload_valido_pdf():
    payload = ContestacaoPorPeticao.model_validate(_payload())
    assert payload.arquivo_peticao_nome == "peticao.pdf"
    assert payload.modelo_base_base64 is None
    assert payload.tipo_acao_hint is None


def test_payload_valido_docx():
    docx_b64 = base64.b64encode(_docx_bytes_minimo()).decode("ascii")
    payload = ContestacaoPorPeticao.model_validate(
        _payload(arquivo_peticao_base64=docx_b64, arquivo_peticao_nome="peticao.docx")
    )
    assert payload.arquivo_peticao_nome == "peticao.docx"


def test_arquivo_muito_grande():
    """Conteudo decodificado > 20MB deve falhar."""
    grande = b"%PDF-1.4\n" + b"a" * (MAX_FILE_SIZE_BYTES + 100)
    b64 = base64.b64encode(grande).decode("ascii")
    with pytest.raises(ValidationError) as exc:
        ContestacaoPorPeticao.model_validate(
            _payload(arquivo_peticao_base64=b64)
        )
    assert "20MB" in str(exc.value)


def test_extensao_invalida():
    with pytest.raises(ValidationError) as exc:
        ContestacaoPorPeticao.model_validate(
            _payload(arquivo_peticao_nome="peticao.txt")
        )
    assert "PDF, DOC ou DOCX" in str(exc.value)


def test_base64_invalido():
    with pytest.raises(ValidationError) as exc:
        ContestacaoPorPeticao.model_validate(
            _payload(arquivo_peticao_base64="!!!nao-eh-base64!!!")
        )
    assert "base64" in str(exc.value).lower()


def test_magic_bytes_invalidos():
    """Base64 valido, mas conteudo nao tem header de PDF/DOC/DOCX."""
    fake = base64.b64encode(b"texto cru sem magic bytes" * 10).decode("ascii")
    with pytest.raises(ValidationError) as exc:
        ContestacaoPorPeticao.model_validate(
            _payload(arquivo_peticao_base64=fake)
        )
    assert "PDF, DOC ou DOCX" in str(exc.value)


def test_path_traversal_no_nome():
    payload = ContestacaoPorPeticao.model_validate(
        _payload(arquivo_peticao_nome="../../etc/passwd/peticao.pdf")
    )
    assert "/" not in payload.arquivo_peticao_nome
    assert payload.arquivo_peticao_nome == "peticao.pdf"


def test_modelo_base_nao_docx_e_rejeitado():
    pdf_b64 = base64.b64encode(_pdf_bytes_minimo()).decode("ascii")
    with pytest.raises(ValidationError) as exc:
        ContestacaoPorPeticao.model_validate(
            _payload(modelo_base_base64=pdf_b64, modelo_base_nome="modelo.pdf")
        )
    assert ".docx" in str(exc.value)


def test_modelo_base_docx_valido_aceito():
    docx_b64 = base64.b64encode(_docx_bytes_minimo()).decode("ascii")
    payload = ContestacaoPorPeticao.model_validate(
        _payload(modelo_base_base64=docx_b64, modelo_base_nome="modelo_escritorio.docx")
    )
    assert payload.modelo_base_nome == "modelo_escritorio.docx"


def test_tipo_acao_hint_e_pontos_normalizam_strings_vazias():
    payload = ContestacaoPorPeticao.model_validate(
        _payload(tipo_acao_hint="   ", pontos_contestante="\n\n")
    )
    assert payload.tipo_acao_hint is None
    assert payload.pontos_contestante is None


def test_tipo_acao_hint_preserva_conteudo():
    payload = ContestacaoPorPeticao.model_validate(
        _payload(tipo_acao_hint="  Trabalhista — Horas Extras  ")
    )
    assert payload.tipo_acao_hint == "Trabalhista — Horas Extras"


def test_extra_fields_sao_ignorados():
    """ConfigDict(extra='ignore') — payload com campo desconhecido nao falha."""
    payload = ContestacaoPorPeticao.model_validate(
        _payload(campo_desconhecido="qualquer coisa")
    )
    assert not hasattr(payload, "campo_desconhecido")
