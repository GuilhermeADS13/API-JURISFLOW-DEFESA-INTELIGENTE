"""Testes do parser de scripts/importar_leis_ctresb.py (base de legislacao do RAG).

Fixtures reproduzem o formato real do repositorio ctresb/leis: Markdown com
cabecalho YAML, artigos em '**Art. N.**' e sumulas extraidas de PDF (OCR).
"""

from __future__ import annotations

import scripts.importar_leis_ctresb as imp

CLT = """---
titulo: "Decreto-Lei nº 5.452 de 01/05/1943"
revogada: false
---
# Decreto-Lei nº 5.452 de 01/05/1943

**Art. 1º** Fica aprovada a Consolidação das Leis do Trabalho.

**Art. 2º** Este decreto-lei entrará em vigor em 10 de novembro de 1943.

**CONSOLIDAÇÃO DAS LEIS DO TRABALHO**

**TÍTULO I**

**INTRODUÇÃO**

**Art. 1º** Esta Consolidação estatui as normas que regulam as relações individuais e coletivas de trabalho.

**Art. 2º** Considera-se empregador a empresa. *(Redação dada pela Lei nº 13.467, de 13/7/2017)*

§ 1º Equiparam-se ao empregador os profissionais liberais.

**Art. 17.** *(Revogado pela Lei nº 13.874, de 20/9/2019)*

**CAPÍTULO II**

**Art. 477-A.** As dispensas imotivadas individuais equiparam-se para todos os fins.

**Art. 818.** O ônus da prova incumbe: *("Caput" do artigo com redação dada pela Lei nº 13.467, de 13/7/2017)*

I - ao reclamante, quanto ao fato constitutivo de seu direito;
"""

CF = """---
titulo: "Constituição"
---
**Art. 7º** São direitos dos trabalhadores urbanos e rurais:

XXIX - ação, quanto aos créditos resultantes das relações de trabalho, com prazo prescricional de cinco anos.

# ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS

**Art. 1º** O Presidente da República prestará o compromisso de manter a Constituição.
"""

SUMULA = """---
titulo: "Súmula nº 338 do TST"
tipo: "Súmula"
numero: "338"
revogada: false
---
# Súmula nº 338 do TST

SUM-338 JORNADA DE TRABALHO. REGISTRO. ÔNUS DA PRO-
VA - Res. 129/2005
I - É ônus do empregador que conta com mais de 10 (dez) emprega-
dos o registro da jornada de trabalho.
Histórico:
Redação original - Res. 36/1994
Nº 338 Registro de horário. Texto antigo que nao pode entrar.
"""

SUMULA_CANCELADA = SUMULA.replace("revogada: false", "revogada: true")


def _por_numero(itens):
    return {numero: texto for numero, texto in itens}


def test_lei_usa_a_consolidacao_e_nao_os_artigos_do_decreto_que_a_aprova():
    artigos = _por_numero(imp.parse_lei(CLT))
    assert artigos["art. 1"].startswith("Esta Consolidação estatui")
    assert artigos["art. 2"].startswith("Considera-se empregador")


def test_lei_descarta_revogados_e_limpa_anotacoes_e_titulos():
    artigos = _por_numero(imp.parse_lei(CLT))
    assert "art. 17" not in artigos
    assert "Redação dada" not in artigos["art. 2"]
    assert "§ 1º Equiparam-se" in artigos["art. 2"]
    assert "CAPÍTULO" not in artigos["art. 2"]
    assert "art. 477-A" in artigos
    assert artigos["art. 818"].startswith("O ônus da prova incumbe:")
    assert "I - ao reclamante" in artigos["art. 818"]


def test_artigo_longo_e_dividido_em_partes():
    longo = "**Art. 5º** Todos são iguais perante a lei.\n\n" + "\n\n".join(
        f"{i} - inciso {'x' * 300}" for i in range(1, 15)
    )
    partes = imp.parse_lei(longo)
    assert len(partes) > 1
    assert partes[0][0] == "art. 5 (parte 1)"
    assert all(len(texto) <= imp.MAX_CHARS for _, texto in partes)


def test_constituicao_separa_o_adct():
    itens = imp.parse_cf(CF)
    origens = {(origem, numero) for origem, numero, _ in itens}
    assert ("CF/88", "art. 7") in origens
    assert ("ADCT", "art. 1") in origens


def test_sumula_junta_hifenizacao_e_corta_historico():
    item = imp.parse_sumula(SUMULA)
    assert item is not None
    numero, texto = item
    assert numero == "338"
    assert "ÔNUS DA PROVA" in texto
    assert "empregados o registro" in texto
    assert "Histórico" not in texto
    assert "Texto antigo" not in texto


def test_sumula_cancelada_e_ignorada():
    assert imp.parse_sumula(SUMULA_CANCELADA) is None
