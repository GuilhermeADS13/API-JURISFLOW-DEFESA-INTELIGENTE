"""Golden tests do extrator de seções jurídicas (PR12 #14).

Garante que `prefiltrar_secoes_juridicas` continue identificando corretamente
as seções principais de petições brasileiras quando os patterns regex em
`SECOES_PRIORIZADAS` forem ajustados. Cada fixture em `golden_petitions/`
representa um caso de uso real do escritório (horas extras, verbas
rescisórias, dano moral) e declara, num `.expected.json`, quais seções
DEVEM ser encontradas, quais NÃO devem, e um snippet característico de cada
uma para garantir que a captura não está pegando o cabeçalho errado.

Adicionar nova fixture: criar `{nome}.txt` + `{nome}.expected.json` no mesmo
diretório. O teste detecta automaticamente via glob.

Por que aqui e não no n8n: o extrator Claude depende de API externa (caro,
não-determinístico, dependente de chave). A pré-filtragem regex e o
truncamento inteligente são determinísticos e cobrem ~80% dos bugs de
extração — é onde os testes pagam.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from App.services.peticao_extractor import (
    MAX_TEXTO_PETICAO_CHARS,
    _aplicar_long_context,
    prefiltrar_secoes_juridicas,
)

GOLDEN_DIR = Path(__file__).parent / "golden_petitions"


def _carregar_fixtures() -> list[tuple[str, str, dict]]:
    """Coleta (nome_fixture, texto_peticao, expected_json) de cada par .txt/.expected.json."""
    casos = []
    for txt_path in sorted(GOLDEN_DIR.glob("*.txt")):
        expected_path = txt_path.with_suffix(".expected.json")
        if not expected_path.exists():
            continue
        texto = txt_path.read_text(encoding="utf-8")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        casos.append((txt_path.stem, texto, expected))
    return casos


FIXTURES = _carregar_fixtures()


def test_diretorio_golden_tem_fixtures():
    """Sanity check: golden_petitions/ nao foi acidentalmente esvaziado."""
    assert len(FIXTURES) >= 3, (
        f"Esperava >=3 fixtures em {GOLDEN_DIR}, achei {len(FIXTURES)}. "
        "Cada fixture e um par .txt + .expected.json."
    )


@pytest.mark.parametrize("nome,texto,expected", FIXTURES, ids=[c[0] for c in FIXTURES])
def test_secoes_obrigatorias_detectadas(nome, texto, expected):
    """Cada seção declarada em sections_present deve ser detectada."""
    secoes = prefiltrar_secoes_juridicas(texto)
    detectadas = set(secoes.keys())
    esperadas = set(expected.get("sections_present", []))
    faltando = esperadas - detectadas
    assert not faltando, (
        f"[{nome}] secoes nao detectadas: {sorted(faltando)}. "
        f"Detectadas: {sorted(detectadas)}"
    )


@pytest.mark.parametrize("nome,texto,expected", FIXTURES, ids=[c[0] for c in FIXTURES])
def test_secoes_proibidas_nao_detectadas(nome, texto, expected):
    """Seções declaradas em sections_absent não podem ser detectadas (falso positivo do regex)."""
    secoes = prefiltrar_secoes_juridicas(texto)
    detectadas = set(secoes.keys())
    proibidas = set(expected.get("sections_absent", []))
    intrusas = detectadas & proibidas
    assert not intrusas, (
        f"[{nome}] secoes detectadas indevidamente (falsos positivos do regex): "
        f"{sorted(intrusas)}"
    )


@pytest.mark.parametrize("nome,texto,expected", FIXTURES, ids=[c[0] for c in FIXTURES])
def test_conteudo_amostral_dentro_da_secao_correta(nome, texto, expected):
    """Snippet característico declarado em sample_text_in_section deve aparecer dentro
    do bloco correto. Garante que a captura não está pegando texto vizinho errado."""
    secoes = prefiltrar_secoes_juridicas(texto)
    samples = expected.get("sample_text_in_section", {})
    for secao, snippet in samples.items():
        assert secao in secoes, (
            f"[{nome}] secao {secao} nao detectada (mas tem sample esperado)"
        )
        assert snippet in secoes[secao], (
            f"[{nome}] snippet esperado da secao {secao} nao encontrado.\n"
            f"  Esperado: {snippet!r}\n"
            f"  Conteudo capturado (primeiros 300 chars): "
            f"{secoes[secao][:300]!r}"
        )


@pytest.mark.parametrize("nome,texto,_expected", FIXTURES, ids=[c[0] for c in FIXTURES])
def test_aplicar_long_context_preserva_pedidos_e_valor_causa(nome, texto, _expected):
    """Quando texto excede limite, _aplicar_long_context deve preservar PEDIDOS
    e VALOR DA CAUSA — perda de qualquer um destes seria deal-breaker pro
    extrator Claude (perde tipo_acao e valor)."""
    # Forca pre-filtragem inflando o texto pra passar do limite
    texto_inflado = texto * (1 + (MAX_TEXTO_PETICAO_CHARS // max(len(texto), 1)))
    if len(texto_inflado) <= MAX_TEXTO_PETICAO_CHARS:
        pytest.skip("fixture pequena demais pra disparar long-context")

    resultado = _aplicar_long_context(texto_inflado, MAX_TEXTO_PETICAO_CHARS)
    # PEDIDOS aparece literalmente em todas as fixtures
    assert "PEDIDOS" in resultado.upper(), (
        f"[{nome}] long-context perdeu a secao PEDIDOS — deal-breaker pro extrator"
    )
    # VALOR DA CAUSA aparece em todas as fixtures
    assert "valor" in resultado.lower(), (
        f"[{nome}] long-context perdeu menção a 'valor' — checar prefiltragem"
    )


def test_prefiltragem_retorna_dict_vazio_para_texto_sem_secoes():
    """Edge case: texto que nao parece peticao (ex: comentario solto) -> {}."""
    texto = "Comentario qualquer sem cabecalho de secao. Apenas prosa livre."
    assert prefiltrar_secoes_juridicas(texto) == {}


def test_prefiltragem_retorna_dict_vazio_para_string_vazia():
    """Edge case: input vazio."""
    assert prefiltrar_secoes_juridicas("") == {}
    assert prefiltrar_secoes_juridicas("   \n\n  ") == {}
