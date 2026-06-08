"""Testes do contestacao_docx_builder, com foco no ROL DE DOCUMENTOS (PR14).

Strategy: invocar `montar_docx_programatico` com diferentes shapes de
`documentos_anexos` e inspecionar os paragrafos do .docx resultante.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document


def _dados_minimos():
    return {
        "numero_processo": "0001234-56.2026.5.06.0001",
        "autor": "Joao da Silva",
        "reu": "Empresa XYZ LTDA",
        "tipo_acao": "Trabalhista",
        "vara": "1a Vara do Trabalho de Recife",
    }


def _minuta_minima(**extra):
    base = {
        "tese_central": "Improcedencia",
        "preliminares": "Prescricao quinquenal.",
        "merito": "Os pedidos carecem de fundamento.",
        "fundamentos": "Art. 818 CLT.",
        "pedidos": "Improcedencia total.",
    }
    base.update(extra)
    return base


def _texto_do_docx(bytes_docx: bytes) -> str:
    """Concatena todos os paragrafos do docx pra busca por substring."""
    doc = Document(BytesIO(bytes_docx))
    return "\n".join(p.text for p in doc.paragraphs)


# ─────────────────────────────────────────────────────────────────────────────
# PR14 — Rol de Documentos
# ─────────────────────────────────────────────────────────────────────────────


def test_rol_de_documentos_aparece_quando_anexos_preenchidos():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    anexos = [
        {
            "numero": "Doc. 01",
            "tipo": "Folha de Ponto",
            "descricao": "Cartoes de ponto do periodo de 01/2020 a 11/2025.",
        },
        {
            "numero": "Doc. 02",
            "tipo": "Extrato FGTS",
            "descricao": "Extrato analitico da CEF do periodo contratual.",
        },
    ]

    docx_bytes = montar_docx_programatico(
        _dados_minimos(),
        _minuta_minima(documentos_anexos=anexos),
    )
    texto = _texto_do_docx(docx_bytes)

    assert "ROL DE DOCUMENTOS" in texto
    assert "Folha de Ponto" in texto
    assert "Extrato FGTS" in texto
    # Cada item gera placeholder visual pro advogado
    assert texto.count("[ANEXAR ARQUIVO]") == 2
    # Descricoes presentes
    assert "Cartoes de ponto do periodo" in texto
    assert "Extrato analitico" in texto


def test_rol_omitido_quando_anexos_ausente():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    # Sem campo documentos_anexos
    docx_bytes = montar_docx_programatico(_dados_minimos(), _minuta_minima())
    texto = _texto_do_docx(docx_bytes)

    assert "ROL DE DOCUMENTOS" not in texto
    assert "[ANEXAR ARQUIVO]" not in texto


def test_rol_omitido_quando_lista_vazia():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    docx_bytes = montar_docx_programatico(
        _dados_minimos(), _minuta_minima(documentos_anexos=[])
    )
    texto = _texto_do_docx(docx_bytes)

    assert "ROL DE DOCUMENTOS" not in texto


def test_rol_descarta_itens_malformados():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    anexos = [
        {"numero": "Doc. 01", "tipo": "Folha de Ponto", "descricao": "Valida."},
        "string solta — invalida",
        {},  # dict sem tipo nem descricao — invalido
        None,  # invalido
        {"tipo": "TRCT", "descricao": "valida sem numero"},  # valido (numero default)
    ]

    docx_bytes = montar_docx_programatico(
        _dados_minimos(), _minuta_minima(documentos_anexos=anexos)
    )
    texto = _texto_do_docx(docx_bytes)

    # 2 itens validos -> 2 placeholders
    assert texto.count("[ANEXAR ARQUIVO]") == 2
    assert "Folha de Ponto" in texto
    assert "TRCT" in texto


def test_rol_cap_em_10_itens():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    anexos = [
        {"numero": f"Doc. {i:02d}", "tipo": f"Tipo {i}", "descricao": f"Desc {i}."}
        for i in range(1, 16)  # 15 itens — alem do cap
    ]

    docx_bytes = montar_docx_programatico(
        _dados_minimos(), _minuta_minima(documentos_anexos=anexos)
    )
    texto = _texto_do_docx(docx_bytes)

    # Cap em 10 itens — 11+ nao aparecem
    assert texto.count("[ANEXAR ARQUIVO]") == 10
    assert "Tipo 10" in texto
    assert "Tipo 11" not in texto


def test_rol_aceita_so_descricao_sem_tipo():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    anexos = [
        {"descricao": "Documento generico sem tipo formal."},
    ]

    docx_bytes = montar_docx_programatico(
        _dados_minimos(), _minuta_minima(documentos_anexos=anexos)
    )
    texto = _texto_do_docx(docx_bytes)

    assert "Documento generico sem tipo formal." in texto
    assert texto.count("[ANEXAR ARQUIVO]") == 1


def test_rol_numera_default_quando_numero_ausente():
    from App.services.contestacao_docx_builder import montar_docx_programatico

    anexos = [
        {"tipo": "A", "descricao": "primeiro"},
        {"tipo": "B", "descricao": "segundo"},
    ]

    docx_bytes = montar_docx_programatico(
        _dados_minimos(), _minuta_minima(documentos_anexos=anexos)
    )
    texto = _texto_do_docx(docx_bytes)

    # numeracao default 'Doc. 01', 'Doc. 02'
    assert "Doc. 01" in texto
    assert "Doc. 02" in texto


def test_rol_nao_renderiza_quando_anexos_nao_eh_lista():
    """Robustez: se Claude retornar dict ou string em vez de list, NAO quebra."""
    from App.services.contestacao_docx_builder import montar_docx_programatico

    for valor_invalido in ("string", {"foo": "bar"}, 42):
        docx_bytes = montar_docx_programatico(
            _dados_minimos(),
            _minuta_minima(documentos_anexos=valor_invalido),
        )
        texto = _texto_do_docx(docx_bytes)
        assert "ROL DE DOCUMENTOS" not in texto
