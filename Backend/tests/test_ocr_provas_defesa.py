"""Testes do OCR das provas da defesa (arquivos_embedar -> texto para a IA).

Mockam `ocr_documento_prova` para nao depender do binario Tesseract no ambiente
de teste; validam so a logica de consolidacao/rotulagem e o default do toggle.
"""

from App.models.contestacao_por_peticao import ContestacaoPorPeticao
from App.services import peticao_extractor as pe


def test_ler_provas_ia_default_true():
    # A opcao "IA le as provas" vem ligada por padrao.
    assert ContestacaoPorPeticao.model_fields["ler_provas_ia"].default is True


def test_consolidar_texto_provas_monta_bloco_rotulado(monkeypatch):
    textos = {
        "trct.png": "TRCT - Saldo de salario R$ 713,36 - rescisao a pedido do empregado",
        "foto.jpg": "   ",  # foto pura, sem texto legivel
    }
    monkeypatch.setattr(
        pe, "ocr_documento_prova", lambda conteudo, nome: textos.get(nome, "")
    )

    provas = [
        {"nome": "trct.png", "tipo": "trct", "conteudo": b"x"},
        {"nome": "foto.jpg", "tipo": "print", "conteudo": b"y"},
    ]
    bloco = pe.consolidar_texto_provas(provas)

    assert "DOCUMENTOS DE PROVA JUNTADOS PELA RECLAMADA" in bloco
    assert "TRCT (Termo de Rescisao)" in bloco  # rotulo mapeado do tipo
    assert "713,36" in bloco  # dado real do documento chegou
    assert "foto.jpg" not in bloco  # prova sem texto foi pulada


def test_consolidar_texto_provas_lista_vazia():
    assert pe.consolidar_texto_provas([]) == ""


def test_consolidar_texto_provas_todas_sem_texto(monkeypatch):
    monkeypatch.setattr(pe, "ocr_documento_prova", lambda conteudo, nome: "")
    provas = [{"nome": "a.png", "tipo": "outro", "conteudo": b"z"}]
    assert pe.consolidar_texto_provas(provas) == ""


def test_consolidar_texto_provas_respeita_cap_por_documento(monkeypatch):
    monkeypatch.setattr(pe, "OCR_PROVA_MAX_CHARS", 20)
    monkeypatch.setattr(pe, "ocr_documento_prova", lambda conteudo, nome: "A" * 500)
    bloco = pe.consolidar_texto_provas(
        [{"nome": "x.png", "tipo": "outro", "conteudo": b"q"}]
    )
    # 20 chars do doc + cabecalho/rotulo; garante que truncou o corpo do documento.
    assert "A" * 20 in bloco
    assert "A" * 21 not in bloco
