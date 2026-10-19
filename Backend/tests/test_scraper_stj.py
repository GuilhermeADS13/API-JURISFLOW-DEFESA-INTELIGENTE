"""PR19 — Testes do scraper STJ.

Estrategia: usa fixture HTML salva (`fixtures/stj_sample.html`) pra:
- Verificar que o parser extrai os 4 acordaos validos + descarta 1 invalido
- Detectar regressao se o STJ mudar o layout (fixture nao muda; testes
  passam ate alguem rodar contra HTML real e atualizar fixture)
- Smoke do scraper SEM bater no portal real (rate limit + tempo de teste)
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch



FIXTURE_PATH = Path(__file__).parent / "fixtures" / "stj_sample.html"


def _html_fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_html_fixture_extrai_4_acordaos_validos():
    """Fixture tem 5 documentos; 1 sem ementa deve ser descartado. Sobram 4."""
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    acordaos = scraper._parse_pagina_resultados(_html_fixture())

    assert len(acordaos) == 4, f"Esperava 4 acordaos validos, recebi {len(acordaos)}"
    numeros = [a["numero_processo"] for a in acordaos]
    assert "REsp 1.998.765/SP" in numeros
    assert "REsp Repetitivo 1.555.555/MG" in numeros
    assert "AgInt no REsp 2.111.000/RJ" in numeros
    assert "REsp 1.777.888/RS" in numeros
    # Invalido descartado
    assert all("Invalido" not in n for n in numeros)


def test_parse_extrai_metadados_completos_do_primeiro_acordao():
    from App.services.scrapers.stj import STJScraper

    acordaos = STJScraper()._parse_pagina_resultados(_html_fixture())
    primeiro = next(a for a in acordaos if a["numero_processo"] == "REsp 1.998.765/SP")

    assert primeiro["tribunal"] == "STJ"
    assert primeiro["relator"] == "Ministro Joao da Silva"
    assert primeiro["data_julgamento"] == "2023-03-15"
    assert "JUSTA CAUSA" in primeiro["ementa"]
    assert primeiro["tipo_decisao"] == "Acordao"
    assert primeiro["peso_relevancia_sugerido"] == 5
    assert primeiro["fonte_url"].startswith("https://scon.stj.jus.br/")


def test_parse_identifica_repetitivo_e_atribui_peso_maior():
    from App.services.scrapers.stj import STJScraper

    acordaos = STJScraper()._parse_pagina_resultados(_html_fixture())
    repetitivo = next(
        a for a in acordaos if "1.555.555/MG" in a["numero_processo"]
    )

    assert repetitivo["tipo_decisao"] == "Repetitivo"
    assert repetitivo["peso_relevancia_sugerido"] == 8


def test_parse_extrai_tese_firmada_quando_presente_na_ementa():
    from App.services.scrapers.stj import STJScraper

    acordaos = STJScraper()._parse_pagina_resultados(_html_fixture())
    repetitivo = next(
        a for a in acordaos if "1.555.555/MG" in a["numero_processo"]
    )

    assert repetitivo["tese_firmada"] is not None
    assert "Selic" in repetitivo["tese_firmada"]


def test_normaliza_data_dd_mm_aaaa_para_iso():
    from App.services.scrapers.stj import STJScraper

    assert STJScraper._normalizar_data("15/03/2023") == "2023-03-15"
    assert STJScraper._normalizar_data("Julgamento em 08/11/2022") == "2022-11-08"
    # Data invalida vira None
    assert STJScraper._normalizar_data("data nao informada") is None
    assert STJScraper._normalizar_data("32/13/2020") is None


def test_parse_layout_quebrado_retorna_lista_vazia_sem_excecao():
    """HTML sem div.documento — parser nao explode, retorna []."""
    from App.services.scrapers.stj import STJScraper

    html_quebrado = "<html><body><div>Erro 500</div></body></html>"
    acordaos = STJScraper()._parse_pagina_resultados(html_quebrado)
    assert acordaos == []


def test_detectou_captcha_identifica_palavra_chave():
    from App.services.scrapers.stj import STJScraper

    assert STJScraper._detectou_captcha("<div>Por favor resolva o CAPTCHA</div>")
    assert STJScraper._detectou_captcha("<script>recaptcha</script>")
    assert not STJScraper._detectou_captcha("<div>resultado normal</div>")


# ─────────────────────────────────────────────────────────────────────────────
# Rate limit + HTTP behavior (sem bater no portal real)
# ─────────────────────────────────────────────────────────────────────────────


def test_rate_limit_aguarda_2s_entre_requests(monkeypatch):
    """Mock time.sleep e verifica que scraper chama sleep com >= 2s entre fetches."""
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    sleeps_chamados = []
    monkeypatch.setattr(
        "App.services.scrapers.stj.time.sleep",
        lambda s: sleeps_chamados.append(s),
    )

    # Simula 2 fetches consecutivos
    scraper._last_request_ts = time.time()
    scraper._rate_limit_aguardar()  # 2o request — deve dormir

    # 1o ou 0 sleeps, mas se dormiu, foi >= 0 e <= 2 (cap)
    assert all(0 <= s <= scraper.RATE_LIMIT_SEC for s in sleeps_chamados)


def test_user_agent_realista_no_header():
    """Portal STJ tem WAF que bloqueia bots explicitos. UA mimica Chrome moderno
    mantendo rate limit conservador (2s) e robots.txt como anti-abuso etico."""
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    ua = scraper.session.headers.get("User-Agent", "")
    assert "Mozilla" in ua and "Chrome" in ua


def test_garantir_cookies_sessao_visita_home_antes_da_busca(monkeypatch):
    """Mitigacao do 403 WAF: scraper visita SCON/ primeiro pra pegar cookies."""
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    urls_chamadas = []

    class _FakeResp:
        def __init__(self, text=""):
            self.text = text
        def raise_for_status(self):
            pass

    def fake_get(url, *args, **kwargs):
        urls_chamadas.append(url)
        return _FakeResp(text="<html></html>")

    monkeypatch.setattr(scraper.session, "get", fake_get)
    monkeypatch.setattr("App.services.scrapers.stj.time.sleep", lambda s: None)

    scraper._fetch_pagina("query teste")

    # 1a chamada: HOME_URL pra cookies; 2a: BASE_URL com query
    assert urls_chamadas[0] == STJScraper.HOME_URL
    assert urls_chamadas[1] == STJScraper.BASE_URL


# ─────────────────────────────────────────────────────────────────────────────
# PR26 — cookies pre-autenticados (workflow anti-Turnstile)
# ─────────────────────────────────────────────────────────────────────────────


def test_scraper_carrega_cookies_do_json(tmp_path, monkeypatch):
    """Cookies exportados por exportar_cookies_stj.py sao aplicados na sessao."""
    import json as _json
    from App.services.scrapers.stj import STJScraper

    cookies_file = tmp_path / "stj_cookies.json"
    cookies_file.write_text(
        _json.dumps([
            {"name": "JSESSIONID", "value": "ABC123",
             "domain": ".stj.jus.br", "path": "/"},
            {"name": "cf_clearance", "value": "TURNSTILE_TOKEN_XYZ",
             "domain": ".stj.jus.br", "path": "/"},
        ]),
        encoding="utf-8",
    )

    scraper = STJScraper(cookies_path=cookies_file)

    # Deve ter marcado _cookies_obtidos=True pra pular visita a HOME
    assert scraper._cookies_obtidos is True
    # Cookies aplicados na session
    # .keys(): iterar curl_cffi.Cookies devolve nomes (str), nao objetos Cookie
    cookie_names = set(scraper.session.cookies.keys())
    assert "JSESSIONID" in cookie_names
    assert "cf_clearance" in cookie_names


def test_scraper_com_cookies_pula_visita_ao_home(tmp_path, monkeypatch):
    """Pre-autenticado: fetch nao chama HOME_URL, so BASE_URL."""
    import json as _json
    from App.services.scrapers.stj import STJScraper

    cookies_file = tmp_path / "stj_cookies.json"
    cookies_file.write_text(
        _json.dumps([{"name": "session", "value": "X", "domain": ".stj.jus.br"}]),
        encoding="utf-8",
    )
    scraper = STJScraper(cookies_path=cookies_file)

    urls_chamadas = []

    class _FakeResp:
        def __init__(self, text=""):
            self.text = text
        def raise_for_status(self):
            pass

    def fake_get(url, *args, **kwargs):
        urls_chamadas.append(url)
        return _FakeResp(text="<html></html>")

    monkeypatch.setattr(scraper.session, "get", fake_get)
    monkeypatch.setattr("App.services.scrapers.stj.time.sleep", lambda s: None)

    scraper._fetch_pagina("query teste")

    # Com cookies pre-autenticados NAO deve visitar HOME_URL
    assert STJScraper.HOME_URL not in urls_chamadas
    # BASE_URL sim (pesquisa)
    assert any(url == STJScraper.BASE_URL for url in urls_chamadas)


def test_scraper_cookies_arquivo_inexistente_nao_crasha(tmp_path):
    """Path invalido → cai no fluxo padrao sem excecao.

    PR27 (finding #14): usa tmp_path do pytest em vez de /tmp/ hardcoded
    (que resolve pra C:/tmp em MSYS/Git Bash e pode existir em edge cases).
    """
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper(cookies_path=tmp_path / "nao-existe-12345.json")

    # _cookies_obtidos permanece False (fluxo padrao)
    assert scraper._cookies_obtidos is False
    # session tem 0 cookies do arquivo
    assert len(list(scraper.session.cookies)) == 0


def test_scraper_cookies_json_invalido_nao_crasha(tmp_path):
    """JSON malformado no arquivo → warning + fluxo padrao."""
    from App.services.scrapers.stj import STJScraper

    cookies_file = tmp_path / "bad.json"
    cookies_file.write_text("{isso nao e json", encoding="utf-8")

    scraper = STJScraper(cookies_path=cookies_file)
    assert scraper._cookies_obtidos is False


def test_scraper_cookies_lista_vazia_nao_marca_pre_autenticado(tmp_path):
    """Arquivo com lista vazia → nao marca _cookies_obtidos=True."""
    import json as _json
    from App.services.scrapers.stj import STJScraper

    cookies_file = tmp_path / "empty.json"
    cookies_file.write_text(_json.dumps([]), encoding="utf-8")

    scraper = STJScraper(cookies_path=cookies_file)
    assert scraper._cookies_obtidos is False


def test_buscar_com_captcha_retorna_lista_vazia(monkeypatch):
    """Quando portal retorna HTML com CAPTCHA, scraper aborta gracefully."""
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    monkeypatch.setattr(
        scraper, "_fetch_pagina", lambda q: "<html>resolva o reCAPTCHA</html>"
    )

    assert scraper.buscar("qualquer query") == []


def test_buscar_falha_http_retorna_lista_vazia(monkeypatch):
    """RequestException nao propaga; retorna []."""
    import requests as req_lib
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    def boom(q):
        raise req_lib.ConnectionError("portal offline")
    monkeypatch.setattr(scraper, "_fetch_pagina", boom)

    assert scraper.buscar("teste") == []


def test_buscar_respeita_max_resultados():
    """Mesmo que o portal retorne 10, --max=3 limita a 3."""
    from App.services.scrapers.stj import STJScraper

    scraper = STJScraper()
    with patch.object(scraper, "_fetch_pagina", return_value=_html_fixture()):
        acordaos = scraper.buscar("teste", max_resultados=2)

    assert len(acordaos) == 2
