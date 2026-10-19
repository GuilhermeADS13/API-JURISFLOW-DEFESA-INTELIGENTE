"""PR34 — Testes do CARFScraper (Solr publico do CARF, jurisprudencia tributaria).

Usa fixture JSON real (`fixtures/carf_sample.json`) pra testar o parser sem
bater na rede. Detecta regressao se o Solr mudar o shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


FIXTURE = Path(__file__).parent / "fixtures" / "carf_sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_resposta_extrai_2_acordaos():
    from App.services.scrapers.carf import CARFScraper

    acordaos = CARFScraper()._parse_resposta(_fixture())
    assert len(acordaos) == 2
    for a in acordaos:
        assert a["tribunal"] == "CARF"
        assert a["numero_processo"]
        assert a["ementa"]
        assert a["tipo_decisao"] == "Acordao"
        assert a["peso_relevancia_sugerido"] in (5, 7)


def test_parse_mapeia_campos_do_primeiro():
    from App.services.scrapers.carf import CARFScraper

    a = CARFScraper()._parse_resposta(_fixture())[0]
    # numero citavel vem de numero_decisao_s (ex: 107-07356 / 9101-002.402)
    assert a["numero_processo"] and "-" in a["numero_processo"]
    # relator title-cased
    assert a["relator"] and a["relator"][0].isupper()
    # data ISO YYYY-MM-DD (Solr manda timestamp completo)
    assert a["data_julgamento"] is not None
    assert len(a["data_julgamento"]) == 10
    assert a["data_julgamento"][4] == "-" and a["data_julgamento"][7] == "-"
    # CARF nao tem tese distinta
    assert a["tese_firmada"] is None
    # fonte_url escopado no acordao especifico (busca pelo numero), nao portal generico
    assert "acordaos.economia.gov.br" in a["fonte_url"]
    assert "numero_decisao_s" in a["fonte_url"]
    # extra informativo: processo administrativo preservado
    assert "numero_processo_administrativo" in a


def test_fonte_url_cai_pro_processo_quando_sem_decisao():
    from App.services.scrapers.carf import CARFScraper

    resp = {
        "response": {
            "docs": [
                {"numero_processo_s": "10925.900663/2006-51", "ementa_s": "ementa x"},
            ]
        }
    }
    a = CARFScraper()._parse_resposta(resp)[0]
    assert "numero_processo_s" in a["fonte_url"]


def test_title_case_respeita_preposicoes():
    from App.services.scrapers.carf import CARFScraper

    assert CARFScraper._title_case("MARCOS AURELIO VALADAO") == "Marcos Aurelio Valadao"
    assert CARFScraper._title_case("joao de souza e silva") == "Joao de Souza e Silva"
    assert CARFScraper._title_case("") is None
    assert CARFScraper._title_case(None) is None


def test_data_iso_corta_timestamp_e_rejeita_invalido():
    from App.services.scrapers.carf import CARFScraper

    assert CARFScraper._data_iso("2016-08-16T00:00:00Z") == "2016-08-16"
    assert CARFScraper._data_iso("2016-08-16") == "2016-08-16"
    assert CARFScraper._data_iso("data ruim") is None
    assert CARFScraper._data_iso(None) is None


def test_campo_aceita_lista_ou_string():
    """Solr pode devolver um campo como str OU como lista de 1 elemento."""
    from App.services.scrapers.carf import CARFScraper

    assert CARFScraper._campo("texto") == "texto"
    assert CARFScraper._campo(["primeiro", "segundo"]) == "primeiro"
    assert CARFScraper._campo([]) == ""
    assert CARFScraper._campo(None) == ""


def test_parse_doc_sem_ementa_ou_numero_e_descartado():
    from App.services.scrapers.carf import CARFScraper

    resp = {
        "response": {
            "docs": [
                {"numero_decisao_s": "9101-1", "ementa_s": "ementa valida aqui"},
                {"numero_decisao_s": "9101-2", "ementa_s": ""},  # sem ementa
                {"numero_decisao_s": "", "ementa_s": "tem ementa mas sem numero"},
            ]
        }
    }
    out = CARFScraper()._parse_resposta(resp)
    assert len(out) == 1
    assert out[0]["numero_processo"] == "9101-1"


def test_numero_cai_pro_processo_quando_sem_decisao():
    from App.services.scrapers.carf import CARFScraper

    resp = {
        "response": {
            "docs": [
                {"numero_processo_s": "10925.900663/2006-51", "ementa_s": "ementa x"},
            ]
        }
    }
    a = CARFScraper()._parse_resposta(resp)[0]
    assert a["numero_processo"] == "10925.900663/2006-51"


def test_parse_resposta_vazia_ou_malformada_retorna_lista():
    from App.services.scrapers.carf import CARFScraper

    s = CARFScraper()
    assert s._parse_resposta({}) == []
    assert s._parse_resposta({"response": {"docs": []}}) == []
    assert s._parse_resposta({"response": {"docs": [None, {}]}}) == []
    assert s._parse_resposta("nao eh dict") == []


def test_peso_maior_na_camara_superior():
    from App.services.scrapers.carf import CARFScraper

    resp = {
        "response": {
            "docs": [
                {
                    "numero_decisao_s": "9101-CSRF",
                    "ementa_s": "ementa csrf",
                    "secao_s": "Camara Superior de Recursos Fiscais",
                },
                {
                    "numero_decisao_s": "3301-ORD",
                    "ementa_s": "ementa ordinaria",
                    "secao_s": "Terceira Secao de Julgamento",
                },
            ]
        }
    }
    csrf, ordinaria = CARFScraper()._parse_resposta(resp)
    assert csrf["peso_relevancia_sugerido"] == 7
    assert ordinaria["peso_relevancia_sugerido"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# buscar() — sem bater na rede real
# ─────────────────────────────────────────────────────────────────────────────


def test_buscar_query_vazia_retorna_lista_vazia():
    from App.services.scrapers.carf import CARFScraper

    assert CARFScraper().buscar("") == []
    assert CARFScraper().buscar("   ") == []


def test_buscar_respeita_max_resultados():
    from App.services.scrapers.carf import CARFScraper

    scraper = CARFScraper()
    with patch.object(scraper, "_fetch_pagina", return_value=_fixture()):
        # fixture tem 2; pede 1
        acordaos = scraper.buscar("qualquer", max_resultados=1)
    assert len(acordaos) == 1


def test_buscar_falha_http_retorna_lista_vazia():
    import requests
    from App.services.scrapers.carf import CARFScraper

    scraper = CARFScraper()

    def boom(*a, **kw):
        raise requests.ConnectionError("offline")

    with patch.object(scraper, "_fetch_pagina", side_effect=boom):
        assert scraper.buscar("PIS COFINS") == []


def test_buscar_para_quando_pagina_vazia(monkeypatch):
    """Se o Solr retorna docs=[] numa pagina, para (nao loopa infinito)."""
    from App.services.scrapers.carf import CARFScraper

    scraper = CARFScraper()
    chamadas = {"n": 0}

    def fake_fetch(query, start, rows):
        chamadas["n"] += 1
        return {"response": {"docs": []}}

    monkeypatch.setattr(scraper, "_fetch_pagina", fake_fetch)
    monkeypatch.setattr(scraper, "_rate_limit_aguardar", lambda: None)

    assert scraper.buscar("nada", max_resultados=50) == []
    assert chamadas["n"] == 1  # parou na 1a pagina vazia


def test_user_agent_e_accept_json():
    from App.services.scrapers.carf import CARFScraper

    h = CARFScraper().session.headers
    assert "Mozilla" in h.get("User-Agent", "")
    assert "json" in h.get("Accept", "").lower()
