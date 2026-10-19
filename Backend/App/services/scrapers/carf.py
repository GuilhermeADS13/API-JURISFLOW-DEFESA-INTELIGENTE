"""Scraper de jurisprudencia TRIBUTARIA do CARF via Apache Solr publico (PR34).

Descoberta (2026-07-27): o portal de acordaos do CARF
(`acordaos.economia.gov.br`) e servido por um Apache Solr cujo endpoint
`/solr/acordaos2/select` responde JSON publico:
  - NAO tem Cloudflare (ao contrario do STJ)
  - NAO exige autenticacao
  - ~580 mil acordaos tributarios (IRPJ, CSLL, PIS/COFINS, IPI, ISS...)
  - Campos limpos: ementa_s, numero_decisao_s, numero_processo_s,
    nome_relator_s, dt_sessao_tdt, secao_s/camara_s/turma_s

Endpoint:
    GET https://acordaos.economia.gov.br/solr/acordaos2/select
        ?q=<termos>&defType=edismax&qf=ementa_s^3 decisao_txt
        &rows=N&wt=json&fl=<campos>

Como o STJ (Turnstile) esta bloqueado pra tributario, o CARF vira a fonte
tributaria primaria. Usa `requests` puro — sem browser, sem cookies.

Etica/anti-abuso: rate limit 1.5s entre requests, User-Agent identificado,
cap de max_resultados. Jurisprudencia e publica (art. 93, IX, CF).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class CARFScraper:
    """Coleta acordaos tributarios do CARF via Solr."""

    BASE_URL = "https://acordaos.economia.gov.br/solr/acordaos2/select"
    PORTAL_URL = "https://acordaos.economia.gov.br/solr/acordaos2/browse/"
    RATE_LIMIT_SEC = 1.5
    TIMEOUT_SEC = 30
    TRIBUNAL = "CARF"
    PAGE_SIZE = 20
    PESO_ACORDAO = 5
    PESO_CSRF = 7  # Camara Superior de Recursos Fiscais = instancia maxima do CARF

    # campos pedidos ao Solr (evita puxar conteudo_txt gigante com metadados de PDF)
    FL = (
        "numero_decisao_s,numero_processo_s,nome_relator_s,dt_sessao_tdt,"
        "secao_s,camara_s,turma_s,ementa_s,ano_sessao_s"
    )

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
                "Accept": "application/json",
            }
        )
        self._last_request_ts: float = 0.0

    def buscar(self, query: str, *, max_resultados: int = 20) -> list[dict[str, Any]]:
        """Pesquisa `query` na jurisprudencia tributaria do CARF.

        Retorna lista de dicts no shape padrao dos scrapers do projeto
        (mesmo do TSTScraper): tribunal, tipo_decisao, numero_processo,
        relator, data_julgamento, ementa, tese_firmada, fonte_url,
        peso_relevancia_sugerido.

        Falha graciosa: erro de rede/parse -> lista vazia + log.
        """
        if not query or not query.strip():
            return []
        max_resultados = max(1, min(int(max_resultados), 100))

        acordaos: list[dict[str, Any]] = []
        start = 0
        while len(acordaos) < max_resultados:
            faltam = max_resultados - len(acordaos)
            rows = min(self.PAGE_SIZE, faltam)
            logger.info(
                "CARF scraper: query=%r start=%d rows=%d (coletados=%d/%d)",
                query,
                start,
                rows,
                len(acordaos),
                max_resultados,
            )
            try:
                data = self._fetch_pagina(query, start, rows)
            except Exception as err:  # noqa: BLE001 — rede/JSON
                logger.error("CARF scraper: falha HTTP/JSON: %s", err)
                break

            lote = self._parse_resposta(data)
            if not lote:
                logger.info("CARF scraper: start=%d sem resultados — fim", start)
                break
            acordaos.extend(lote)
            start += rows
            if start > 1000:  # guarda contra loop
                break

        return acordaos[:max_resultados]

    # ─────────────────────────── Internos ────────────────────────────────

    def _rate_limit_aguardar(self) -> None:
        agora = time.time()
        delta = agora - self._last_request_ts
        if delta < self.RATE_LIMIT_SEC:
            time.sleep(self.RATE_LIMIT_SEC - delta)
        self._last_request_ts = time.time()

    def _fetch_pagina(self, query: str, start: int, rows: int) -> dict[str, Any]:
        """GET paginado no Solr. Retorna o JSON decodificado (dict)."""
        self._rate_limit_aguardar()
        params = {
            "q": query,
            "defType": "edismax",
            "qf": "ementa_s^3 decisao_txt",
            "start": start,
            "rows": rows,
            "wt": "json",
            "fl": self.FL,
        }
        resp = self.session.get(self.BASE_URL, params=params, timeout=self.TIMEOUT_SEC)
        resp.raise_for_status()
        return resp.json()

    def _parse_resposta(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrai acordaos da resposta Solr. Tolerante a campos ausentes."""
        if not isinstance(data, dict):
            return []
        docs = (data.get("response") or {}).get("docs") or []
        out: list[dict[str, Any]] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            acordao = self._map_doc(doc)
            if acordao is not None:
                out.append(acordao)
        return out

    def _map_doc(self, doc: dict[str, Any]) -> dict[str, Any] | None:
        """Mapeia 1 doc Solr do CARF pro shape padrao do projeto."""
        ementa = self._campo(doc.get("ementa_s")).strip()
        # numero citavel do acordao (ex: 9101-002.402); fallback pro processo
        num_decisao = self._campo(doc.get("numero_decisao_s")).strip()
        num_processo = self._campo(doc.get("numero_processo_s")).strip()
        numero = num_decisao or num_processo
        if not ementa or not numero:
            return None

        relator = self._title_case(doc.get("nome_relator_s"))
        data_iso = self._data_iso(doc.get("dt_sessao_tdt"))
        secao = self._campo(doc.get("secao_s"))

        # peso: Camara Superior (CSRF) pesa mais que turmas ordinarias
        peso = self.PESO_CSRF if "superior" in secao.lower() else self.PESO_ACORDAO

        # orgao julgador legivel (secao + turma quando houver)
        turma = self._campo(doc.get("turma_s"))
        orgao = " - ".join(p for p in (secao, turma) if p) or None

        # fonte_url aponta pro acordao especifico (busca Solr pelo campo/numero
        # que identifica este registro), nao pro portal generico.
        if num_decisao:
            fonte_url = self._fonte_url("numero_decisao_s", num_decisao)
        else:
            fonte_url = self._fonte_url("numero_processo_s", num_processo)

        return {
            "tribunal": self.TRIBUNAL,
            "tipo_decisao": "Acordao",
            "numero_processo": numero,
            "relator": relator,
            "data_julgamento": data_iso,
            "ementa": ementa,
            "tese_firmada": None,  # a ementa_s do CARF ja traz assunto + tese
            "fonte_url": fonte_url,
            "peso_relevancia_sugerido": peso,
            # extras informativos (nao usados pelo upsert)
            "orgao_judicante": orgao,
            "numero_processo_administrativo": num_processo or None,
        }

    @classmethod
    def _fonte_url(cls, campo: str, valor: str) -> str:
        """Link de busca Solr escopado no acordao (campo:\"valor\")."""
        q = requests.utils.quote(f'{campo}:"{valor}"')
        return f"{cls.PORTAL_URL}?q={q}"

    @staticmethod
    def _campo(v: Any) -> str:
        """Solr pode devolver campo como str ou lista de 1 elemento."""
        if isinstance(v, list):
            return str(v[0]) if v else ""
        return str(v or "")

    @classmethod
    def _title_case(cls, nome: Any) -> str | None:
        """'MARCOS AURELIO VALADAO' -> 'Marcos Aurelio Valadao'. None -> None."""
        s = cls._campo(nome).strip()
        if not s:
            return None
        minus = {"de", "da", "do", "das", "dos", "e"}
        return " ".join(p if p in minus else p.capitalize() for p in s.lower().split())

    @classmethod
    def _data_iso(cls, raw: Any) -> str | None:
        """Extrai YYYY-MM-DD do dt_sessao_tdt (ISO com timestamp)."""
        s = cls._campo(raw).strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        return None
