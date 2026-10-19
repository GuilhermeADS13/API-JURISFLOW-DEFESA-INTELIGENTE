"""Scraper de jurisprudencia do TST via API REST publica (PR31).

Descoberta (sniff 2026-07-08): a SPA `jurisprudencia.tst.jus.br` consome uma
API REST em `jurisprudencia-backend2.tst.jus.br` que:
  - NAO tem Cloudflare (ao contrario do STJ)
  - NAO exige autenticacao
  - Retorna JSON limpo com ementa + numero + relator + data + texto integral
  - Cobre ~360 mil acordaos trabalhistas

Endpoint de busca:
    POST https://jurisprudencia-backend2.tst.jus.br/rest/pesquisa-textual/{pagina}/{tamanho}
    Content-Type: application/json
    Body: {"e": "<termos>", "tipos": ["ACORDAO"], "orgao": "TST", ...(resto null/[])}

Resposta:
    {"tempoGasto": ..., "totalRegistros": 360796,
     "registros": [{"registro": {ementa, numFormatado, nomRelator, dtaJulgamento,
                                  tipo, orgaoJudicante, txtInteiroTeor, ...},
                    "destaques": {...}}, ...],
     "agregacoes": {...}}

Por isso este scraper usa `requests` puro — sem curl_cffi, sem Playwright,
sem cookies. Roda no container/cron sem intervencao. Muito mais simples e
robusto que o STJScraper (que briga com Turnstile).

Etica/anti-abuso: rate limit 1.5s entre requests, User-Agent identificado,
cap de max_resultados. Jurisprudencia eh publica (art. 93 IX CF).
"""

from __future__ import annotations

import logging
import time
import unicodedata
from typing import Any

import requests

logger = logging.getLogger(__name__)


class TSTScraper:
    """Coleta acordaos do TST via API REST de jurisprudencia."""

    BASE_URL = "https://jurisprudencia-backend2.tst.jus.br/rest/pesquisa-textual"
    FRONT_URL = "https://jurisprudencia.tst.jus.br/"
    RATE_LIMIT_SEC = 1.5
    TIMEOUT_SEC = 30
    TRIBUNAL = "TST"
    # Tamanho de pagina pedido a API (API aceita ate ~50 sem problema)
    PAGE_SIZE = 20
    PESO_ACORDAO = 5
    PESO_COM_TEMA = 7  # acordao com tema de repercussao/repetitivo pesa mais

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://jurisprudencia.tst.jus.br",
                "Referer": self.FRONT_URL,
            }
        )
        self._last_request_ts: float = 0.0

    def buscar(self, query: str, *, max_resultados: int = 20) -> list[dict[str, Any]]:
        """Pesquisa `query` na jurisprudencia do TST e retorna acordaos.

        Retorna lista de dicts no shape padrao dos scrapers do projeto
        (mesmo do STJScraper): tribunal, tipo_decisao, numero_processo,
        relator, data_julgamento, ementa, tese_firmada, fonte_url,
        peso_relevancia_sugerido.

        Falha graciosa: erro de rede/parse -> lista vazia + log.
        """
        if not query or not query.strip():
            return []
        max_resultados = max(1, min(int(max_resultados), 100))

        acordaos: list[dict[str, Any]] = []
        pagina = 1
        while len(acordaos) < max_resultados:
            faltam = max_resultados - len(acordaos)
            tamanho = min(self.PAGE_SIZE, faltam)
            logger.info(
                "TST scraper: query=%r pagina=%d tamanho=%d (coletados=%d/%d)",
                query,
                pagina,
                tamanho,
                len(acordaos),
                max_resultados,
            )
            try:
                data = self._fetch_pagina(query, pagina, tamanho)
            except Exception as err:  # noqa: BLE001 — rede/JSON
                logger.error("TST scraper: falha HTTP/JSON: %s", err)
                break

            lote = self._parse_resposta(data)
            if not lote:
                logger.info("TST scraper: pagina %d sem resultados — fim", pagina)
                break
            acordaos.extend(lote)
            pagina += 1
            # Guarda contra loop infinito se a API repetir
            if pagina > 50:
                break

        return acordaos[:max_resultados]

    # ─────────────────────────── Internos ────────────────────────────────

    def _rate_limit_aguardar(self) -> None:
        agora = time.time()
        delta = agora - self._last_request_ts
        if delta < self.RATE_LIMIT_SEC:
            time.sleep(self.RATE_LIMIT_SEC - delta)
        self._last_request_ts = time.time()

    def _build_body(self, query: str) -> dict[str, Any]:
        """Monta o payload JSON da busca (replica o que a SPA envia)."""
        return {
            "ou": None,
            "e": query,
            "termoExato": "",
            "naoContem": None,
            "ementa": None,
            "dispositivo": None,
            "numeracaoUnica": {
                "numero": None,
                "digito": None,
                "ano": None,
                "orgao": "5",
                "tribunal": None,
                "vara": None,
            },
            "orgaosJudicantes": [],
            "ministros": [],
            "convocados": [],
            "classesProcessuais": [],
            "indicadores": [],
            "assuntos": [],
            "tipos": ["ACORDAO"],
            "orgao": "TST",
        }

    def _fetch_pagina(self, query: str, pagina: int, tamanho: int) -> dict[str, Any]:
        """POST paginado. Retorna o JSON decodificado (dict)."""
        self._rate_limit_aguardar()
        url = f"{self.BASE_URL}/{pagina}/{tamanho}"
        resp = self.session.post(
            url,
            json=self._build_body(query),
            timeout=self.TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_resposta(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrai acordaos da resposta JSON. Tolerante a campos ausentes."""
        if not isinstance(data, dict):
            return []
        registros = data.get("registros") or []
        out: list[dict[str, Any]] = []
        for wrapper in registros:
            reg = (wrapper or {}).get("registro") if isinstance(wrapper, dict) else None
            if not isinstance(reg, dict):
                continue
            acordao = self._map_registro(reg)
            if acordao is not None:
                out.append(acordao)
        return out

    def _map_registro(self, reg: dict[str, Any]) -> dict[str, Any] | None:
        """Mapeia 1 registro da API pro shape padrao do projeto."""
        ementa = str(reg.get("ementa") or "").strip()
        numero = str(reg.get("numFormatado") or "").strip()
        # Sem ementa nem numero nao serve pro RAG — descarta
        if not ementa or not numero:
            return None

        relator = self._title_case(reg.get("nomRelator"))
        data_iso = self._data_iso(reg.get("dtaJulgamento"))
        tipo = self._tipo_decisao(reg.get("tipo"))
        orgao_judicante = None
        oj = reg.get("orgaoJudicante")
        if isinstance(oj, dict):
            orgao_judicante = oj.get("descricao")

        # Peso: acordao com tema vinculante/repetitivo pesa mais
        temas = reg.get("temaProcs") or []
        peso = self.PESO_COM_TEMA if temas else self.PESO_ACORDAO

        # tese_firmada: TST nao tem campo distinto; usa o 1o tema quando houver
        tese = None
        if temas and isinstance(temas, list) and isinstance(temas[0], dict):
            tese = str(temas[0].get("descricao") or "").strip() or None

        fonte_url = self._fonte_url(numero)

        return {
            "tribunal": self.TRIBUNAL,
            "tipo_decisao": tipo,
            "numero_processo": numero,
            "relator": relator,
            "data_julgamento": data_iso,
            "ementa": ementa,
            "tese_firmada": tese,
            "fonte_url": fonte_url,
            "peso_relevancia_sugerido": peso,
            # extra util pro contexto (nao usado pelo upsert, mas informativo)
            "orgao_judicante": orgao_judicante,
        }

    @staticmethod
    def _title_case(nome: Any) -> str | None:
        """'maria helena mallmann' -> 'Maria Helena Mallmann'. None -> None."""
        s = str(nome or "").strip()
        if not s:
            return None
        # preposicoes ficam minusculas
        minus = {"de", "da", "do", "das", "dos", "e"}
        partes = s.lower().split()
        return " ".join(p if p in minus else p.capitalize() for p in partes)

    @staticmethod
    def _data_iso(raw: Any) -> str | None:
        """Extrai YYYY-MM-DD. API ja manda ISO; corta hora/timezone."""
        s = str(raw or "").strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        return None

    @staticmethod
    def _tipo_decisao(tipo: Any) -> str:
        """Normaliza tipo.nome removendo acentos. 'Acórdão' -> 'Acordao'.

        O resto do projeto usa tipos sem acento (Acordao, Sumula, OJ-SDI...).
        Strip de diacriticos casa com essa convencao.
        """
        if isinstance(tipo, dict):
            nome = str(tipo.get("nome") or "").strip()
            if nome:
                sem_acento = "".join(
                    c
                    for c in unicodedata.normalize("NFKD", nome)
                    if not unicodedata.combining(c)
                )
                return sem_acento
        return "Acordao"

    @classmethod
    def _fonte_url(cls, numero: str) -> str:
        """URL de referencia pra busca no portal do TST."""
        return f"{cls.FRONT_URL}?e={requests.utils.quote(numero)}"
