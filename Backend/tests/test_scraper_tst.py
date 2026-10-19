"""PR31 — Testes do TSTScraper (API REST publica do TST).

Usa fixture JSON real (`fixtures/tst_sample.json`) pra testar o parser sem
bater na rede. Detecta regressao se a API mudar o shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch



FIXTURE = Path(__file__).parent / "fixtures" / "tst_sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_resposta_extrai_2_acordaos():
    from App.services.scrapers.tst import TSTScraper

    acordaos = TSTScraper()._parse_resposta(_fixture())
    assert len(acordaos) == 2
    for a in acordaos:
        assert a["tribunal"] == "TST"
        assert a["numero_processo"]
        assert a["ementa"]
        assert a["peso_relevancia_sugerido"] in (5, 7)


def test_parse_mapeia_campos_do_primeiro():
    from App.services.scrapers.tst import TSTScraper

    a = TSTScraper()._parse_resposta(_fixture())[0]
    # numero vem de numFormatado
    assert "-" in a["numero_processo"] and "." in a["numero_processo"]
    # relator title-cased (fixture tem "amaury rodrigues pinto junior")
    assert a["relator"] and a["relator"][0].isupper()
    # data ISO YYYY-MM-DD (fixture tem timestamp completo)
    assert a["data_julgamento"] is not None
    assert len(a["data_julgamento"]) == 10
    assert a["data_julgamento"][4] == "-"
    # tipo sem acento
    assert a["tipo_decisao"] == "Acordao"
    # fonte_url aponta pro TST
    assert "jurisprudencia.tst.jus.br" in a["fonte_url"]


def test_title_case_respeita_preposicoes():
    from App.services.scrapers.tst import TSTScraper

    assert TSTScraper._title_case("maria helena mallmann") == "Maria Helena Mallmann"
    assert TSTScraper._title_case("joao de souza e silva") == "Joao de Souza e Silva"
    assert TSTScraper._title_case("") is None
    assert TSTScraper._title_case(None) is None


def test_data_iso_corta_timestamp_e_rejeita_invalido():
    from App.services.scrapers.tst import TSTScraper

    assert TSTScraper._data_iso("2026-05-27T09:00:00-03") == "2026-05-27"
    assert TSTScraper._data_iso("2026-05-27") == "2026-05-27"
    assert TSTScraper._data_iso("data ruim") is None
    assert TSTScraper._data_iso(None) is None


def test_tipo_decisao_normaliza_acento():
    from App.services.scrapers.tst import TSTScraper

    assert TSTScraper._tipo_decisao({"nome": "Acordão"}) == "Acordao"
    assert TSTScraper._tipo_decisao({"nome": "Despacho"}) == "Despacho"
    assert TSTScraper._tipo_decisao(None) == "Acordao"


def test_parse_registro_sem_ementa_ou_numero_e_descartado():
    from App.services.scrapers.tst import TSTScraper

    resp = {
        "totalRegistros": 3,
        "registros": [
            {"registro": {"numFormatado": "RR-1", "ementa": "ementa valida aqui"}},
            {"registro": {"numFormatado": "RR-2", "ementa": ""}},        # sem ementa
            {"registro": {"numFormatado": "", "ementa": "tem ementa"}},   # sem numero
        ],
    }
    out = TSTScraper()._parse_resposta(resp)
    assert len(out) == 1
    assert out[0]["numero_processo"] == "RR-1"


def test_parse_resposta_vazia_ou_malformada_retorna_lista():
    from App.services.scrapers.tst import TSTScraper

    s = TSTScraper()
    assert s._parse_resposta({}) == []
    assert s._parse_resposta({"registros": []}) == []
    assert s._parse_resposta({"registros": [None, {}, {"registro": None}]}) == []
    assert s._parse_resposta("nao eh dict") == []


def test_peso_maior_quando_tem_tema():
    from App.services.scrapers.tst import TSTScraper

    resp = {
        "registros": [
            {"registro": {
                "numFormatado": "RR-9", "ementa": "ementa com tema vinculante",
                "temaProcs": [{"descricao": "Tema 1046 - terceirizacao"}],
            }},
        ],
    }
    a = TSTScraper()._parse_resposta(resp)[0]
    assert a["peso_relevancia_sugerido"] == 7
    assert a["tese_firmada"] == "Tema 1046 - terceirizacao"


# ─────────────────────────────────────────────────────────────────────────────
# buscar() — sem bater na rede real
# ─────────────────────────────────────────────────────────────────────────────


def test_buscar_query_vazia_retorna_lista_vazia():
    from App.services.scrapers.tst import TSTScraper

    assert TSTScraper().buscar("") == []
    assert TSTScraper().buscar("   ") == []


def test_buscar_respeita_max_resultados():
    from App.services.scrapers.tst import TSTScraper

    scraper = TSTScraper()
    with patch.object(scraper, "_fetch_pagina", return_value=_fixture()):
        # fixture tem 2; pede 1
        acordaos = scraper.buscar("qualquer", max_resultados=1)
    assert len(acordaos) == 1


def test_buscar_falha_http_retorna_lista_vazia():
    import requests
    from App.services.scrapers.tst import TSTScraper

    scraper = TSTScraper()
    def boom(*a, **kw):
        raise requests.ConnectionError("offline")
    with patch.object(scraper, "_fetch_pagina", side_effect=boom):
        assert scraper.buscar("horas extras") == []


def test_buscar_para_quando_pagina_vazia(monkeypatch):
    """Se a API retorna registros=[] numa pagina, para (nao loopa infinito)."""
    from App.services.scrapers.tst import TSTScraper

    scraper = TSTScraper()
    chamadas = {"n": 0}
    def fake_fetch(query, pagina, tamanho):
        chamadas["n"] += 1
        return {"registros": []}  # sempre vazio
    monkeypatch.setattr(scraper, "_fetch_pagina", fake_fetch)
    monkeypatch.setattr(scraper, "_rate_limit_aguardar", lambda: None)

    assert scraper.buscar("nada", max_resultados=50) == []
    assert chamadas["n"] == 1  # parou na 1a pagina vazia


def test_build_body_tem_estrutura_esperada():
    from App.services.scrapers.tst import TSTScraper

    body = TSTScraper()._build_body("rescisao indireta")
    assert body["e"] == "rescisao indireta"
    assert body["tipos"] == ["ACORDAO"]
    assert body["orgao"] == "TST"
    assert "numeracaoUnica" in body


def test_user_agent_e_json_headers():
    from App.services.scrapers.tst import TSTScraper

    h = TSTScraper().session.headers
    assert "Mozilla" in h.get("User-Agent", "")
    assert h.get("Content-Type") == "application/json"
    assert "jurisprudencia.tst.jus.br" in h.get("Referer", "")
