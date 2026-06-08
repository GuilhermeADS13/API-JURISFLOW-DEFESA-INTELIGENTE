"""Testes do PR6 #3 — OCR fallback para PDFs digitalizados (Guia v3 §2.7).

Estrategia: gera um PDF nativo com texto pequeno (simulando PDF digitalizado
de baixa qualidade onde pypdf consegue pouco/nada), valida que:

1. Quando texto pypdf < threshold, OCR e disparado.
2. Quando OCR_ENABLED=false, OCR e bypassado mesmo se texto for curto.
3. Quando libs OCR (pytesseract/pdf2image) nao instaladas, fallback gracioso.

Cobertura util e' testes unitarios da logica de roteamento — testes E2E
contra Tesseract real ficam para a validacao manual no container Docker.
"""

from __future__ import annotations

from io import BytesIO

import pytest


def _criar_pdf_pypdf_pobre() -> bytes:
    """Cria um PDF minimo. pypdf vai retornar texto < threshold,
    simulando PDF digitalizado.
    """
    # Gera PDF minimo via reportlab (so pra ter um arquivo PDF valido). Como
    # o conteudo eh muito pequeno, pypdf deve retornar pouco/nada.
    try:
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf)
        # Escreve so 5 chars — abaixo do PDF_OCR_FALLBACK_THRESHOLD=200.
        c.drawString(100, 100, "Curto")
        c.save()
        return buf.getvalue()
    except ImportError:
        # Fallback: PDF cru minimal (header + 1 page). pypdf abre mas nao acha texto.
        # Magic bytes do PDF + estrutura minima.
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Length 0 >>\nstream\n\nendstream\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000050 00000 n \n0000000100 00000 n \n0000000180 00000 n \n"
            b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n230\n%%EOF\n"
        )


def test_pypdf_curto_aciona_fallback_ocr(monkeypatch):
    """Quando pypdf retorna < threshold, _extrair_pdf_via_ocr e chamado."""
    from App.services import peticao_extractor

    # Forca OCR ligado e simula libs disponiveis.
    monkeypatch.setattr(peticao_extractor, "OCR_ENABLED", True)
    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)

    chamadas_ocr = []

    def fake_ocr(conteudo: bytes) -> str:
        chamadas_ocr.append(len(conteudo))
        return "TEXTO EXTRAIDO POR OCR de uma peticao digitalizada bem comprida " * 10

    monkeypatch.setattr(peticao_extractor, "_extrair_pdf_via_ocr", fake_ocr)

    pdf_bytes = _criar_pdf_pypdf_pobre()
    texto = peticao_extractor._extrair_pdf(pdf_bytes)

    assert len(chamadas_ocr) == 1, "OCR fallback deveria ter sido chamado"
    assert "TEXTO EXTRAIDO POR OCR" in texto


def test_ocr_desligado_nao_aciona_fallback(monkeypatch):
    """OCR_ENABLED=false faz com que o OCR seja bypassado mesmo com texto curto."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "OCR_ENABLED", False)
    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)

    chamadas_ocr = []
    monkeypatch.setattr(
        peticao_extractor,
        "_extrair_pdf_via_ocr",
        lambda c: chamadas_ocr.append(c) or "",
    )

    pdf_bytes = _criar_pdf_pypdf_pobre()
    texto = peticao_extractor._extrair_pdf(pdf_bytes)

    assert len(chamadas_ocr) == 0, "OCR nao deveria ser chamado com OCR_ENABLED=false"
    # Retorna o texto curto do pypdf (nao quebra)
    assert isinstance(texto, str)


def test_libs_ocr_indisponiveis_nao_quebra(monkeypatch):
    """Se pytesseract/pdf2image nao estao instalados, retorna texto curto sem OCR."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "OCR_ENABLED", True)
    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", False)

    pdf_bytes = _criar_pdf_pypdf_pobre()
    # Nao deve levantar excecao — apenas retornar o que pypdf encontrou.
    texto = peticao_extractor._extrair_pdf(pdf_bytes)
    assert isinstance(texto, str)


def test_pypdf_com_texto_suficiente_pula_ocr(monkeypatch):
    """PDF com texto >= threshold nao precisa de OCR — pypdf basta."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "OCR_ENABLED", True)
    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)
    monkeypatch.setattr(peticao_extractor, "PDF_OCR_FALLBACK_THRESHOLD", 50)

    chamadas_ocr = []
    monkeypatch.setattr(
        peticao_extractor,
        "_extrair_pdf_via_ocr",
        lambda c: chamadas_ocr.append(c) or "OCR_NAO_DEVERIA",
    )

    # Gera PDF com texto longo o suficiente. Usamos reportlab se disponivel
    # senao pulamos o teste — eh um caso de regressao.
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab nao instalado")

    buf = BytesIO()
    c = canvas.Canvas(buf)
    texto_grande = (
        "Texto longo o suficiente para pypdf retornar mais que threshold. " * 10
    )
    c.drawString(100, 700, texto_grande)
    c.save()

    texto = peticao_extractor._extrair_pdf(buf.getvalue())

    assert len(chamadas_ocr) == 0, "OCR nao deveria ser chamado quando pypdf basta"
    assert "OCR_NAO_DEVERIA" not in texto


def test_ocr_falha_retorna_texto_pypdf(monkeypatch):
    """Se OCR levanta excecao, fallback retorna texto pypdf (curto) sem quebrar."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "OCR_ENABLED", True)
    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)

    def fake_ocr_quebra(conteudo: bytes) -> str:
        raise RuntimeError("Tesseract nao instalado")

    monkeypatch.setattr(peticao_extractor, "_extrair_pdf_via_ocr", fake_ocr_quebra)

    pdf_bytes = _criar_pdf_pypdf_pobre()
    # Nao levanta excecao — retorna o texto pypdf curto.
    texto = peticao_extractor._extrair_pdf(pdf_bytes)
    assert isinstance(texto, str)


def test_ocr_combina_pypdf_quando_pypdf_tem_algo(monkeypatch):
    """Cabecalho nativo + corpo escaneado: OCR concatena ao pypdf."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "OCR_ENABLED", True)
    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)
    monkeypatch.setattr(
        peticao_extractor, "PDF_OCR_FALLBACK_THRESHOLD", 9999
    )  # forca OCR

    monkeypatch.setattr(
        peticao_extractor,
        "_extrair_pdf_via_ocr",
        lambda c: "TEXTO_OCR_CORPO",
    )

    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab nao instalado")

    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, "TEXTO_PYPDF_CABECALHO")
    c.save()

    texto = peticao_extractor._extrair_pdf(buf.getvalue())
    # Ambos presentes no resultado
    assert "TEXTO_PYPDF_CABECALHO" in texto
    assert "TEXTO_OCR_CORPO" in texto


# ─────────────────────────────────────────────────────────────────────────────
# PR13 #B2: Cache de OCR (SHA-256 do PDF)
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_hit_pula_tesseract(monkeypatch):
    """Quando get_ocr_cache retorna texto, _executar_ocr_real NAO eh chamado."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)

    chamadas_real = []
    monkeypatch.setattr(
        peticao_extractor,
        "_executar_ocr_real",
        lambda c: (chamadas_real.append(c), "NAO_DEVERIA_RODAR")[1],
    )
    monkeypatch.setattr(
        "App.database.get_ocr_cache",
        lambda h: "TEXTO_DO_CACHE",
    )
    set_chamadas = []
    monkeypatch.setattr(
        "App.database.set_ocr_cache",
        lambda h, t, paginas=None: set_chamadas.append((h, len(t))),
    )

    resultado = peticao_extractor._extrair_pdf_via_ocr(b"fake_pdf_bytes")

    assert resultado == "TEXTO_DO_CACHE"
    assert chamadas_real == []  # Tesseract nao rodou
    assert set_chamadas == []  # nao reescreve cache em hit


def test_cache_miss_executa_ocr_e_grava(monkeypatch):
    """Cache vazio -> Tesseract roda + set_ocr_cache eh chamado com hash certo."""
    import hashlib

    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)
    monkeypatch.setattr(peticao_extractor, "_executar_ocr_real", lambda c: "TEXTO_NOVO")
    monkeypatch.setattr("App.database.get_ocr_cache", lambda h: None)

    sets = []
    monkeypatch.setattr(
        "App.database.set_ocr_cache",
        lambda h, t, paginas=None: sets.append((h, t)),
    )

    conteudo = b"pdf_bytes_unicos"
    esperado_hash = hashlib.sha256(conteudo).hexdigest()

    resultado = peticao_extractor._extrair_pdf_via_ocr(conteudo)

    assert resultado == "TEXTO_NOVO"
    assert len(sets) == 1
    assert sets[0] == (esperado_hash, "TEXTO_NOVO")


def test_cache_falha_silenciosa_nao_quebra_extracao(monkeypatch):
    """Se o DB nao responder, OCR continua funcionando — cache eh otimizacao."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)
    monkeypatch.setattr(peticao_extractor, "_executar_ocr_real", lambda c: "TEXTO_OK")

    def boom(_h):
        raise RuntimeError("DB down")

    monkeypatch.setattr("App.database.get_ocr_cache", boom)
    monkeypatch.setattr("App.database.set_ocr_cache", boom)

    # Nao deve levantar; deve retornar o texto do OCR real
    resultado = peticao_extractor._extrair_pdf_via_ocr(b"fake_pdf")
    assert resultado == "TEXTO_OK"


def test_cache_nao_grava_texto_vazio(monkeypatch):
    """Se Tesseract retorna vazio (libs off ou poppler ausente), nao polui o cache."""
    from App.services import peticao_extractor

    monkeypatch.setattr(peticao_extractor, "_OCR_LIBS_DISPONIVEIS", True)
    monkeypatch.setattr(peticao_extractor, "_executar_ocr_real", lambda c: "")
    monkeypatch.setattr("App.database.get_ocr_cache", lambda h: None)
    sets = []
    monkeypatch.setattr(
        "App.database.set_ocr_cache",
        lambda h, t, paginas=None: sets.append((h, t)),
    )

    resultado = peticao_extractor._extrair_pdf_via_ocr(b"fake_pdf")

    assert resultado == ""
    assert sets == []  # nao gravou cache de string vazia


def test_helpers_db_rejeitam_hash_invalido():
    """get_ocr_cache / set_ocr_cache cortam input invalido ANTES de tocar DB."""
    from App import database as db

    # Strings curtas ou vazias devem ser no-op sem inicializar pool
    assert db.get_ocr_cache("") is None
    assert db.get_ocr_cache("curto") is None
    # set_ocr_cache nao explode com hash invalido ou texto vazio
    db.set_ocr_cache("", "texto")
    db.set_ocr_cache("curto", "texto")
    # Hash valido mas texto vazio: tambem deve ser no-op (nao polui cache)
    db.set_ocr_cache("a" * 64, "")
