"""Testes de diff_minuta (PR5 Observabilidade — golden dataset)."""

from __future__ import annotations

from App.services.diff_minuta import diff_secoes, resumo_diff


def test_diff_secoes_iguais_nao_marcam_alterada():
    diff = diff_secoes(
        {"tese_central": "Improcedencia total."},
        {"tese_central": "Improcedencia total."},
    )
    assert diff["tese_central"]["alterada"] is False
    assert diff["tese_central"]["similaridade"] == 1.0


def test_diff_detecta_alteracao_textual():
    diff = diff_secoes(
        {"merito": "O autor nao tem prova."},
        {"merito": "O reclamante nao apresentou prova testemunhal."},
    )
    assert diff["merito"]["alterada"] is True
    assert diff["merito"]["similaridade"] < 1.0
    # SequenceMatcher trabalha em chars, entao concatena para checar substring.
    todo_adicionado = "".join(diff["merito"]["adicionado"])
    assert "testemunhal" in todo_adicionado


def test_diff_secao_ausente_em_ambos_nao_marca_alterada():
    diff = diff_secoes(
        {"tese_central": "X"},
        {"tese_central": "X"},
    )
    assert diff["preliminares"]["alterada"] is False


def test_diff_aceita_dict_em_impugnacao_pedidos():
    """impugnacao_pedidos eh um dict — diff serializa de forma estavel."""
    # impugnacao_pedidos nao esta em SECOES_DIFFEAVEIS, mas a funcao deve
    # aceitar inputs sem quebrar.
    diff = diff_secoes(
        {"tese_central": "Tese", "impugnacao_pedidos": {"a": "1"}},
        {"tese_central": "Tese", "impugnacao_pedidos": {"a": "2"}},
    )
    # tese_central nao mudou
    assert diff["tese_central"]["alterada"] is False


def test_resumo_diff_conta_secoes_alteradas():
    diff = diff_secoes(
        {"tese_central": "A", "merito": "B", "fundamentos": "C"},
        {"tese_central": "A", "merito": "B mudou", "fundamentos": "C"},
    )
    resumo = resumo_diff(diff)
    assert "merito" in resumo["secoes_alteradas"]
    assert resumo["total_secoes_alteradas"] == 1
    assert 0 < resumo["similaridade_media"] < 1.0


def test_resumo_diff_minutas_identicas_similaridade_1():
    diff = diff_secoes(
        {"tese_central": "X", "merito": "Y"},
        {"tese_central": "X", "merito": "Y"},
    )
    resumo = resumo_diff(diff)
    assert resumo["total_secoes_alteradas"] == 0
    assert resumo["similaridade_media"] == 1.0
