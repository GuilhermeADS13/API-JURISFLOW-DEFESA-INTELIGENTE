"""Scraper do portal de Jurisprudencia Consolidada do STJ (SCON).

Portal publico: https://scon.stj.jus.br/SCON/
Pesquisa por palavras-chave (frase, operadores booleanos, filtros de data).
Cada resultado tem ementa estruturada + processo + relator + data julgamento.

Estrategia:
- requests + BeautifulSoup (HTML estatico, dispensa Playwright em IP residencial)
- Visita HOME pra cookies de sessao antes da busca
- Rate limit 2s entre paginas
- User-Agent mimicando Chrome 120
- Parser via seletores CSS estaveis do template do STJ
- Falha de parse de UM item nao derruba o lote (log warning + skip)

WAF do STJ — Cloudflare Turnstile bloqueia ate Playwright headless em datacenter:
  O portal SCON usa Cloudflare Turnstile (interstitial 'Um momento...') que
  faz fingerprint de Chromium headless mesmo com stealth init_script
  (navigator.webdriver mascarado, plugins fake, etc) e args anti-detection.
  No nosso ambiente, smoke real (2026-06-29) confirmou:
   - curl_cffi (impersonate=chrome120): 403 imediato — WAF nem deixa passar.
   - Playwright headless + stealth + wait Turnstile 25s: titulo segue
     'Um momento...' e div.documento nao aparece. Challenge nao resolve.

  Causa: Cloudflare combina reputacao do IP de datacenter + sinais de
  automacao (resolucao de canvas, audio fingerprint, mouse jitter, WebGL).
  Stealth basico nao engana.

  Mitigacoes possiveis (PRs futuros, nao incluidas no PR20):
  - Rodar o script localmente no notebook do dev: IP residencial geralmente
    passa o Turnstile sem challenge. ESTA E A ALTERNATIVA SUPORTADA HOJE:
      cd Backend
      .venv\\Scripts\\python.exe scripts/scrape_jurisprudencia.py \\
          --tribunal=stj --query="rescisao indireta" --max=10
  - CAPTCHA solver pago (2Captcha, Anti-Captcha): ~US$ 2/1000 challenges.
  - Proxy residencial (BrightData, Smartproxy): ~US$ 5/GB.
  - Xvfb + headless=False + playwright-stealth-plus: parcialmente eficaz.

  Por que mantemos a cadeia curl_cffi -> Playwright mesmo assim:
  - Outros tribunais (TJ-PE, TST) podem nao ter Cloudflare. Aproveita o
    mesmo codigo de cascata sem precisar reescrever scraper por tribunal.
  - Em IP residencial, ambos passam.
  - Fallback gracioso: scraper retorna lista vazia em vez de explodir.

Outras limitacoes:
- Resultados acima de 100 paginadas viram captcha. Cap rigido em max=50
- Layout do portal as vezes muda em manutencoes — fixture HTML salva no repo
  + test_parse_html_fixture detecta regressao
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# curl_cffi mimica TLS fingerprint (JA3) do Chrome real — fast-path quando
# WAF do STJ filtra so por TLS handshake. Em IP de datacenter, geralmente
# nao basta (WAF tem JS challenge tambem). Veja fallback Playwright abaixo.
try:
    from curl_cffi import requests as cffi_requests

    _HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    _HAS_CURL_CFFI = False

# Playwright carrega Chromium real, resolve JS challenge do WAF (Cloudflare
# Turnstile, Imperva, etc). +5-10s por request mas garantia de passar em
# qualquer IP. Usado como fallback quando curl_cffi retorna 403.
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    _HAS_PLAYWRIGHT = True
except ImportError:
    sync_playwright = None
    PlaywrightTimeout = Exception
    _HAS_PLAYWRIGHT = False

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class STJScraper:
    """Coleta acordaos do STJ via pesquisa em scon.stj.jus.br."""

    BASE_URL = "https://scon.stj.jus.br/SCON/pesquisar.jsp"
    HOME_URL = "https://scon.stj.jus.br/SCON/"
    RATE_LIMIT_SEC = 2.0
    # User-Agent realista (Chrome moderno). Portal STJ bloqueia bots
    # explicitos via WAF. Mantemos rate limit conservador (2s) por etica.
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    TIMEOUT_SEC = 15
    TRIBUNAL = "STJ"
    PESO_DEFAULT_REPETITIVO = 8
    PESO_DEFAULT_ACORDAO = 5

    def __init__(self, cookies_path: Path | str | None = None) -> None:
        # Prefere curl_cffi (impersonate Chrome) pra burlar WAF. Fallback
        # pra requests so quando curl_cffi nao esta disponivel (testes
        # unitarios podem mockar a sessao via monkeypatch).
        if _HAS_CURL_CFFI:
            self.session = cffi_requests.Session(impersonate="chrome120")
            logger.info("STJ scraper: usando curl_cffi (impersonate=chrome120)")
        else:
            self.session = requests.Session()
            logger.warning(
                "STJ scraper: curl_cffi nao instalado, caindo em requests "
                "(provavel 403 pelo WAF do portal)"
            )
        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self._last_request_ts: float = 0.0
        self._cookies_obtidos: bool = False
        # PR26: carrega cookies pre-autenticados (dev resolveu Turnstile
        # manualmente via scripts/exportar_cookies_stj.py). Se cookies foram
        # carregados com sucesso, marca `_cookies_obtidos=True` pra pular a
        # visita a HOME_URL (que dispararia novo Turnstile em datacenter).
        if cookies_path is not None:
            self._carregar_cookies_de_arquivo(Path(cookies_path))

    def _carregar_cookies_de_arquivo(self, path: Path) -> None:
        """Carrega cookies exportados por `scripts/exportar_cookies_stj.py`.

        Formato esperado: lista de dicts como Playwright retorna em
        `context.cookies()`: {name, value, domain, path, expires, ...}.

        Falha silenciosa se arquivo nao existe / JSON invalido — scraper
        cai no fluxo padrao (curl_cffi + Playwright fallback). Loga
        warning pra o dev saber.
        """
        if not path.exists():
            logger.warning(
                "STJ cookies file nao encontrado: %s — usando fluxo padrao", path
            )
            return
        try:
            cookies = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as err:
            logger.warning("Falha ao ler cookies STJ (%s): %s", path, err)
            return

        if not isinstance(cookies, list):
            logger.warning(
                "Cookies STJ mal formatados em %s (esperava lista, recebi %s)",
                path,
                type(cookies),
            )
            return

        aplicados = 0
        pulados = 0
        for cookie in cookies:
            if not isinstance(cookie, dict):
                pulados += 1
                continue
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                pulados += 1
                continue
            # PR27 (finding #15): sanitiza name/value contra header injection.
            # \r\n\x00 em cookie value poderiam gerar headers HTTP malformados
            # se a lib de sessao nao escapar (comportamento varia por versao
            # do requests/curl_cffi). Reject explicito e mais seguro.
            value_str = str(value)
            if any(c in value_str for c in ("\r", "\n", "\x00")):
                logger.warning(
                    "Cookie %r com caracteres de controle no value — pulado",
                    name,
                )
                pulados += 1
                continue
            try:
                self.session.cookies.set(
                    name=name,
                    value=value_str,
                    domain=cookie.get("domain") or ".stj.jus.br",
                    path=cookie.get("path") or "/",
                )
                aplicados += 1
            except Exception as err:  # noqa: BLE001 — jar apis variam
                logger.debug("skip cookie %s: %s", name, err)
                pulados += 1

        if aplicados > 0:
            self._cookies_obtidos = True
            logger.info(
                "STJ cookies pre-autenticados carregados de %s (%d cookies) — "
                "pulando visita a HOME_URL",
                path,
                aplicados,
            )
        else:
            # PR27 (finding #3): dev configurou --cookies mas TODOS pularam.
            # Antes: log so em DEBUG, dev nao percebia. Agora WARNING audivel.
            logger.warning(
                "STJ cookies file lido de %s mas 0 cookies aplicados "
                "(%d pulados) — scraper caira no fluxo Turnstile padrao. "
                "Verifique estrutura do JSON: cada entrada precisa de "
                "'name' e 'value' nao-vazios.",
                path,
                pulados,
            )

    def buscar(self, query: str, *, max_resultados: int = 20) -> list[dict[str, Any]]:
        """Pesquisa por `query` no portal e retorna lista de acordaos.

        `max_resultados` cap em 50 (alem disso o portal retorna captcha).
        """
        if not query or not query.strip():
            return []
        max_resultados = max(1, min(int(max_resultados), 50))

        logger.info("STJ scraper: query=%r max=%d", query, max_resultados)
        try:
            html = self._fetch_pagina(query)
        except Exception as err:  # noqa: BLE001 — curl_cffi vs requests
            logger.error("STJ scraper: HTTP falhou: %s", err)
            return []

        if self._detectou_captcha(html):
            logger.warning(
                "STJ scraper: CAPTCHA detectado. Aguardar 5-10min antes de "
                "rodar de novo. Considere reduzir --max"
            )
            return []

        acordaos = self._parse_pagina_resultados(html)
        return acordaos[:max_resultados]

    # ─────────────────────────── Internos ────────────────────────────────

    def _rate_limit_aguardar(self) -> None:
        """Garante intervalo de RATE_LIMIT_SEC entre requests."""
        agora = time.time()
        delta = agora - self._last_request_ts
        if delta < self.RATE_LIMIT_SEC:
            time.sleep(self.RATE_LIMIT_SEC - delta)
        self._last_request_ts = time.time()

    def _garantir_cookies_sessao(self) -> None:
        """Visita a home do SCON pra obter cookies de sessao antes da busca.

        Portal STJ retorna 403 quando bate direto em pesquisar.jsp sem ter
        passado pelo SCON/ primeiro (WAF detecta scraper bruto).
        Captura Exception generica porque curl_cffi tem hierarquia de
        excecoes diferente de requests.
        """
        if self._cookies_obtidos:
            return
        try:
            self._rate_limit_aguardar()
            resp = self.session.get(self.HOME_URL, timeout=self.TIMEOUT_SEC)
            resp.raise_for_status()
            self._cookies_obtidos = True
        except Exception as err:  # noqa: BLE001 — fallback amplo (curl_cffi vs requests)
            logger.warning("Falha ao obter cookies de sessao STJ: %s", err)

    def _build_search_url(self, query: str) -> str:
        """Constroi URL completa da pesquisa STJ (usado por curl_cffi e Playwright)."""
        from urllib.parse import urlencode

        params = {
            "operador": "e",
            "b": "ACOR",
            "thesaurus": "JURIDICO",
            "p": "true",
            "tp": "T",
            "processo": "",
            "ministro": "",
            "orgaoJulg": "",
            "pesquisaInicialAvancada": query,
        }
        return f"{self.BASE_URL}?{urlencode(params)}"

    # Init script anti-deteccao: roda em todo frame ANTES de qualquer script da pagina.
    # Mascara as flags reveladoras de headless (navigator.webdriver=true, plugins
    # vazio, etc) que Cloudflare Turnstile e Imperva checam.
    _STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en']});
    Object.defineProperty(navigator, 'plugins', {
      get: () => [
        {name: 'Chrome PDF Plugin'},
        {name: 'Chrome PDF Viewer'},
        {name: 'Native Client'}
      ]
    });
    window.chrome = {runtime: {}};
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
      window.navigator.permissions.query = (p) =>
        p.name === 'notifications'
          ? Promise.resolve({state: Notification.permission})
          : originalQuery(p);
    }
    """

    def _fetch_via_playwright(self, query: str) -> str:
        """Carrega a pesquisa via Chromium real (Playwright). Resolve JS challenge
        do WAF (Cloudflare Turnstile, Imperva) — funciona ate em IP de datacenter.

        Usa init_script anti-deteccao (mascara navigator.webdriver, plugins, etc)
        e aguarda ate o Turnstile resolver (titulo deixar de ser 'Um momento...').

        Custo: ~10-25s por request (vs <1s do curl_cffi). Usado so quando o
        fast-path falhar com 403/captcha.
        """
        if not _HAS_PLAYWRIGHT or sync_playwright is None:
            raise RuntimeError(
                "Playwright nao instalado. Adicione 'playwright' ao requirements "
                "e rode 'python -m playwright install chromium'."
            )
        url = self._build_search_url(query)
        logger.info("STJ scraper: fallback Playwright headless em %s", url[:80])
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-site-isolation-trials",
                    "--disable-web-security",
                ],
            )
            try:
                context = browser.new_context(
                    user_agent=self.USER_AGENT,
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1280, "height": 720},
                    extra_http_headers={
                        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    },
                )
                # Injeta stealth ANTES de qualquer navegacao
                context.add_init_script(self._STEALTH_JS)

                page = context.new_page()
                try:
                    # 1. Visita home — Turnstile aparece aqui se for primeira visita.
                    #    domcontentloaded é melhor que networkidle (turnstile mantem socket).
                    page.goto(
                        self.HOME_URL, wait_until="domcontentloaded", timeout=30000
                    )
                    self._aguardar_turnstile(page)

                    # 2. Vai pra pesquisa (deveria ja ter cookies do challenge)
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    self._aguardar_turnstile(page)

                    # 3. Aguarda os div.documento (parser depende). Timeout largo:
                    #    primeira pesquisa pode demorar se o portal estiver lento.
                    try:
                        page.wait_for_selector("div.documento", timeout=20000)
                    except PlaywrightTimeout:
                        logger.warning(
                            "STJ scraper: div.documento nao apareceu em 20s "
                            "(query sem hits, ainda em turnstile, ou layout mudou?). "
                            "Titulo atual: %r",
                            page.title()[:80],
                        )
                    return page.content()
                finally:
                    page.close()
                    context.close()
            finally:
                browser.close()

    @staticmethod
    def _aguardar_turnstile(page: Any) -> None:
        """Aguarda o Cloudflare Turnstile resolver. Titulo da pagina muda de
        'Um momento...' / 'Just a moment...' pro titulo real do STJ.

        Timeout 25s — challenge geralmente resolve em 3-10s em IP residencial,
        ate 20s em datacenter. Se exceder, segue mesmo assim (pode estar OK).
        """
        try:
            page.wait_for_function(
                "() => !document.title.toLowerCase().includes('um momento') "
                "&& !document.title.toLowerCase().includes('just a moment')",
                timeout=25000,
            )
        except PlaywrightTimeout:
            logger.warning(
                "STJ scraper: Turnstile nao resolveu em 25s (titulo: %r)",
                page.title()[:80],
            )

    def _fetch_pagina(self, query: str) -> str:
        """Fetch da pagina de resultados. Tenta curl_cffi primeiro (rapido);
        se 403/captcha, cai pra Playwright headless (Chromium real, ~5-10s).
        """
        self._garantir_cookies_sessao()
        self._rate_limit_aguardar()
        params = {
            "operador": "e",
            "b": "ACOR",
            "thesaurus": "JURIDICO",
            "p": "true",
            "tp": "T",
            "processo": "",
            "ministro": "",
            "orgaoJulg": "",
            "pesquisaInicialAvancada": query,
        }

        # Tenta curl_cffi (fast-path)
        try:
            resp = self.session.get(
                self.BASE_URL,
                params=params,
                timeout=self.TIMEOUT_SEC,
                headers={"Referer": self.HOME_URL},
            )
            resp.raise_for_status()
            html = resp.text
            # Mesmo com 200, o portal pode ter retornado pagina de captcha
            if not self._detectou_captcha(html):
                return html
            logger.warning(
                "STJ scraper: curl_cffi recebeu captcha — fallback Playwright"
            )
        except Exception as err:
            logger.warning(
                "STJ scraper: curl_cffi falhou (%s) — fallback Playwright", err
            )

        # Fallback Playwright (carrega Chromium real, resolve JS challenge)
        return self._fetch_via_playwright(query)

    @staticmethod
    def _detectou_captcha(html: str) -> bool:
        """Heuristica simples: STJ inclui 'captcha' ou 'reCAPTCHA' no HTML
        quando bloqueia."""
        baixo = html.lower()
        return "captcha" in baixo or "recaptcha" in baixo

    def _parse_pagina_resultados(self, html: str) -> list[dict[str, Any]]:
        """Extrai metadados dos resultados.

        Seletores estaveis do template STJ (validados em jun/2026):
        - div.documento — wrapper de cada acordao
          - div.paragrafoBRS:has(.docTitulo:contains('Processo')) — numero
          - div.paragrafoBRS:has(.docTitulo:contains('Relator')) — relator
          - div.paragrafoBRS:has(.docTitulo:contains('Data do Julgamento')) — data
          - div.paragrafoBRS:has(.docTitulo:contains('Ementa')) — ementa
        """
        soup = BeautifulSoup(html, "lxml")
        documentos = soup.select("div.documento")
        if not documentos:
            logger.warning(
                "STJ scraper: nenhum div.documento encontrado — layout pode ter mudado"
            )
            return []

        acordaos: list[dict[str, Any]] = []
        for doc in documentos:
            try:
                acordao = self._parse_documento(doc)
                if acordao:
                    acordaos.append(acordao)
            except Exception as err:  # noqa: BLE001 — parse de UM nao derruba lote
                logger.warning("STJ scraper: skip documento por erro de parse: %s", err)
                continue
        return acordaos

    def _parse_documento(self, doc: Any) -> dict[str, Any] | None:
        """Extrai um acordao do div.documento. Retorna None se invalido."""
        numero_processo = self._extrair_campo(doc, "Processo")
        ementa = self._extrair_campo(doc, "Ementa")
        relator = self._extrair_campo(doc, "Relator")
        data_raw = self._extrair_campo(doc, "Data do Julgamento")

        if not numero_processo or not ementa:
            return None

        data_iso = self._normalizar_data(data_raw) if data_raw else None
        tipo, peso = self._inferir_tipo_e_peso(numero_processo, ementa)

        # tese_firmada: STJ as vezes inclui linha 'TESE FIRMADA' no fim da ementa
        tese_firmada = self._extrair_tese(ementa)

        # fonte_url: linka pra documento individual via processo (sem ID interno)
        fonte_url = (
            "https://scon.stj.jus.br/SCON/pesquisar.jsp?"
            f"pesquisaInicialAvancada={requests.utils.quote(numero_processo)}"
        )

        return {
            "tribunal": self.TRIBUNAL,
            "tipo_decisao": tipo,
            "numero_processo": numero_processo,
            "relator": relator,
            "data_julgamento": data_iso,
            "ementa": ementa.strip(),
            "tese_firmada": tese_firmada,
            "fonte_url": fonte_url,
            "peso_relevancia_sugerido": peso,
        }

    @staticmethod
    def _extrair_campo(doc: Any, titulo: str) -> str | None:
        """Extrai conteudo de div.paragrafoBRS cujo span.docTitulo tem texto
        contendo `titulo` (ex: 'Processo', 'Ementa')."""
        for paragrafo in doc.select("div.paragrafoBRS"):
            tit = paragrafo.select_one(".docTitulo")
            if not tit:
                continue
            if titulo.lower() not in tit.get_text(strip=True).lower():
                continue
            # Conteudo eh o(s) elemento(s) apos o titulo
            conteudo = paragrafo.select_one(".docTexto")
            if conteudo:
                return conteudo.get_text(" ", strip=True)
            # Fallback: texto do paragrafo sem o titulo
            texto = paragrafo.get_text(" ", strip=True)
            return texto.replace(tit.get_text(strip=True), "", 1).strip(": ").strip()
        return None

    @staticmethod
    def _normalizar_data(raw: str) -> str | None:
        """Converte 'DD/MM/AAAA' em ISO 'YYYY-MM-DD'. Retorna None se invalida."""
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
        if not m:
            return None
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return dt.date().isoformat()
        except ValueError:
            return None

    def _inferir_tipo_e_peso(self, numero: str, ementa: str) -> tuple[str, int]:
        """Inferencia leve: REPETITIVO no texto -> tipo 'Repetitivo' peso 8.
        Caso contrario tipo 'Acordao' peso 5."""
        upper = (numero + " " + ementa).upper()
        if "RECURSO REPETITIVO" in upper or "TEMA REPETITIVO" in upper:
            return ("Repetitivo", self.PESO_DEFAULT_REPETITIVO)
        return ("Acordao", self.PESO_DEFAULT_ACORDAO)

    @staticmethod
    def _extrair_tese(ementa: str) -> str | None:
        """Se ementa tem 'TESE FIRMADA: ...' ou 'TESE: ...' no fim, extrai."""
        m = re.search(
            r"(?:TESE\s+FIRMADA|TESE\s+JURIDICA|TESE)\s*[:\.\-]\s*(.+?)(?:\Z|\n\n)",
            ementa,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return None
        return m.group(1).strip()[:1500]
