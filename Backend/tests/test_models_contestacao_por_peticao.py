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
        ContestacaoPorPeticao.model_validate(_payload(arquivo_peticao_base64=b64))
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
        ContestacaoPorPeticao.model_validate(_payload(arquivo_peticao_base64=fake))
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


# ─────────────────────────────────────────────────────────────────────────────
# PR15 — ArquivoEmbedar + arquivos_embedar (provas embedaveis no docx)
# ─────────────────────────────────────────────────────────────────────────────


def _png_bytes_minimo() -> bytes:
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buf, format="PNG")
    return buf.getvalue()


def _jpg_bytes_minimo() -> bytes:
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buf, format="JPEG")
    return buf.getvalue()


def _embed_item(tipo: str = "fgts", nome: str = "fake.png", b64: str | None = None) -> dict:
    if b64 is None:
        b64 = base64.b64encode(_png_bytes_minimo()).decode("ascii")
    return {"base64": b64, "nome": nome, "mime_type": "image/png", "tipo": tipo}


class TestArquivoEmbedar:
    def test_aceita_png_com_tipo_canonico(self):
        payload = ContestacaoPorPeticao.model_validate(
            _payload(arquivos_embedar=[_embed_item(tipo="fgts")])
        )
        assert len(payload.arquivos_embedar) == 1
        assert payload.arquivos_embedar[0].tipo == "fgts"

    def test_aceita_jpg(self):
        item = _embed_item(
            tipo="folha_ponto",
            nome="ponto.jpg",
            b64=base64.b64encode(_jpg_bytes_minimo()).decode("ascii"),
        )
        payload = ContestacaoPorPeticao.model_validate(
            _payload(arquivos_embedar=[item])
        )
        assert payload.arquivos_embedar[0].nome == "ponto.jpg"

    def test_aceita_pdf(self):
        item = _embed_item(
            tipo="trct",
            nome="trct.pdf",
            b64=base64.b64encode(_pdf_bytes_minimo()).decode("ascii"),
        )
        payload = ContestacaoPorPeticao.model_validate(
            _payload(arquivos_embedar=[item])
        )
        assert payload.arquivos_embedar[0].tipo == "trct"

    def test_rejeita_tipo_invalido(self):
        with pytest.raises(ValidationError, match="tipo invalido"):
            ContestacaoPorPeticao.model_validate(
                _payload(arquivos_embedar=[_embed_item(tipo="marciano")])
            )

    def test_normaliza_tipo_case_insensitive(self):
        payload = ContestacaoPorPeticao.model_validate(
            _payload(arquivos_embedar=[_embed_item(tipo="FGTS")])
        )
        assert payload.arquivos_embedar[0].tipo == "fgts"

    def test_rejeita_extensao_nao_suportada(self):
        item = {
            "base64": base64.b64encode(_png_bytes_minimo()).decode("ascii"),
            "nome": "doc.docx",
            "mime_type": "application/x-doc",
            "tipo": "outro",
        }
        with pytest.raises(ValidationError, match="JPG, JPEG, PNG ou PDF"):
            ContestacaoPorPeticao.model_validate(
                _payload(arquivos_embedar=[item])
            )

    def test_rejeita_base64_com_magic_bytes_invalidos(self):
        item = {
            "base64": base64.b64encode(b"isso_nao_eh_png").decode("ascii"),
            "nome": "fake.png",
            "mime_type": "image/png",
            "tipo": "outro",
        }
        with pytest.raises(ValidationError, match="JPG, PNG ou PDF"):
            ContestacaoPorPeticao.model_validate(
                _payload(arquivos_embedar=[item])
            )

    def test_aceita_lista_vazia_default(self):
        payload = ContestacaoPorPeticao.model_validate(_payload())
        assert payload.arquivos_embedar == []

    def test_rejeita_mais_de_10_arquivos_embedar(self):
        items = [_embed_item(tipo="outro", nome=f"f{i}.png") for i in range(11)]
        with pytest.raises(ValidationError, match="Maximo de 10 arquivos embedaveis"):
            ContestacaoPorPeticao.model_validate(
                _payload(arquivos_embedar=items)
            )

    def test_aceita_exatamente_10(self):
        items = [_embed_item(tipo="outro", nome=f"f{i}.png") for i in range(10)]
        payload = ContestacaoPorPeticao.model_validate(
            _payload(arquivos_embedar=items)
        )
        assert len(payload.arquivos_embedar) == 10

    def test_tipos_canonicos_aceitos(self):
        """Smoke check: todos os tipos canonicos passam pela validacao."""
        from App.models.contestacao_por_peticao import TIPOS_EMBED_CANONICOS

        for tipo in TIPOS_EMBED_CANONICOS:
            payload = ContestacaoPorPeticao.model_validate(
                _payload(arquivos_embedar=[_embed_item(tipo=tipo)])
            )
            assert payload.arquivos_embedar[0].tipo == tipo

