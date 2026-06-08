"""PR15 — testes do embed_processor: decodificacao + conversao PDF -> PNG."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import patch

from PIL import Image


@dataclass
class _FakeArquivo:
    """Mimica ArquivoEmbedar pra evitar dependencia do Pydantic em testes unitarios."""

    base64: str
    nome: str
    tipo: str
    mime_type: str = "image/png"


def _png_b64() -> str:
    buf = BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _jpg_b64() -> str:
    buf = BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _pdf_minimo_b64() -> str:
    # PDF cru minimo — pdf2image talvez nao consiga abrir, mas serve pra teste
    # de bytes (a conversao real eh mockada nos testes que importam).
    return base64.b64encode(b"%PDF-1.4\n%fake-pdf-bytes\n").decode("ascii")


# ─────────────────────────────────────────────────────────────────────────────


def test_lista_vazia_retorna_vazio():
    from App.services.embed_processor import processar_arquivos_embedar

    assert processar_arquivos_embedar([]) == []
    assert processar_arquivos_embedar(None) == []


def test_imagem_png_direta_vira_uma_imagem_embedavel():
    from App.services.embed_processor import processar_arquivos_embedar

    arq = _FakeArquivo(base64=_png_b64(), nome="foto.png", tipo="fgts")
    resultado = processar_arquivos_embedar([arq])

    assert len(resultado) == 1
    img = resultado[0]
    assert img.tipo == "fgts"
    assert img.nome == "foto.png"
    assert img.eh_imagem_direta is True
    assert img.pagina == 1
    assert img.bytes_png.startswith(b"\x89PNG")


def test_imagem_jpg_direta_vira_uma_imagem_embedavel():
    from App.services.embed_processor import processar_arquivos_embedar

    arq = _FakeArquivo(
        base64=_jpg_b64(), nome="trct.jpg", tipo="trct", mime_type="image/jpeg"
    )
    resultado = processar_arquivos_embedar([arq])

    assert len(resultado) == 1
    assert resultado[0].tipo == "trct"
    assert resultado[0].eh_imagem_direta is True
    # JPG eh aceito como-eh (python-docx aceita)
    assert resultado[0].bytes_png[:3] == b"\xff\xd8\xff"  # JPEG SOI


def test_base64_corrompido_eh_descartado_silenciosamente():
    from App.services.embed_processor import processar_arquivos_embedar

    arq = _FakeArquivo(base64="nao_eh_base64_valido!@#", nome="x.png", tipo="outro")
    assert processar_arquivos_embedar([arq]) == []


def test_pdf_vira_uma_imagem_embedavel_por_pagina_mockada(monkeypatch):
    """Mock pdf2image — verifica que cada pagina vira ImagemEmbedavel separada."""
    from App.services import embed_processor

    # Mock _pdf_para_pngs pra retornar 3 PNGs fake
    fake_pngs = [b"\x89PNG" + b"x" * 50 for _ in range(3)]
    monkeypatch.setattr(
        embed_processor, "_pdf_para_pngs", lambda b, *, nome: fake_pngs
    )

    arq = _FakeArquivo(base64=_pdf_minimo_b64(), nome="laudo.pdf", tipo="laudo_pericial")
    resultado = embed_processor.processar_arquivos_embedar([arq])

    assert len(resultado) == 3
    for i, img in enumerate(resultado, start=1):
        assert img.tipo == "laudo_pericial"
        assert img.nome == "laudo.pdf"
        assert img.pagina == i
        assert img.eh_imagem_direta is False


def test_pdf_sem_pdf2image_eh_silenciosamente_descartado(monkeypatch):
    """Quando pdf2image indisponivel, PDFs nao geram imagens (mas nao quebram)."""
    from App.services import embed_processor

    monkeypatch.setattr(embed_processor, "_PDF2IMAGE_DISPONIVEL", False)
    monkeypatch.setattr(embed_processor, "convert_from_bytes", None)

    arq = _FakeArquivo(base64=_pdf_minimo_b64(), nome="x.pdf", tipo="trct")
    resultado = embed_processor.processar_arquivos_embedar([arq])

    assert resultado == []


def test_extensao_nao_reconhecida_eh_descartada():
    from App.services.embed_processor import processar_arquivos_embedar

    # .gif nao esta em ALLOWED_EMBED_EXTENSIONS — defesa em profundidade no service
    arq = _FakeArquivo(base64=_png_b64(), nome="anim.gif", tipo="outro")
    assert processar_arquivos_embedar([arq]) == []


def test_mistura_de_tipos_processada_corretamente(monkeypatch):
    """Lista heterogenea: 2 PNGs + 1 PDF (mockado pra 2 paginas) = 4 ImagemEmbedavel."""
    from App.services import embed_processor

    monkeypatch.setattr(
        embed_processor, "_pdf_para_pngs",
        lambda b, *, nome: [b"\x89PNG" + b"a" * 30, b"\x89PNG" + b"b" * 30],
    )

    arqs = [
        _FakeArquivo(base64=_png_b64(), nome="png1.png", tipo="folha_ponto"),
        _FakeArquivo(base64=_pdf_minimo_b64(), nome="multi.pdf", tipo="laudo_pericial"),
        _FakeArquivo(base64=_jpg_b64(), nome="img.jpg", tipo="print", mime_type="image/jpeg"),
    ]
    resultado = embed_processor.processar_arquivos_embedar(arqs)

    # 1 PNG + 2 paginas do PDF + 1 JPG = 4
    assert len(resultado) == 4
    tipos = [img.tipo for img in resultado]
    assert tipos == ["folha_ponto", "laudo_pericial", "laudo_pericial", "print"]
