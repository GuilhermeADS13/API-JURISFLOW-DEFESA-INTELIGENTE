"""PR21 - Cliente da API publica DataJud do CNJ.

A API publica DataJud (`api-publica.datajud.cnj.jus.br`) eh um Elasticsearch
exposto pelo CNJ com metadados processuais de todos os tribunais brasileiros
(STF, STJ, TST, TJs estaduais, TRTs, TREs, TJMs). Acesso por API key publica
documentada em https://datajud-wiki.cnj.jus.br/api-publica/acesso/.

Quando NAO usar:
  - Pra recuperar EMENTA, TESE, ou TEXTO INTEGRAL de acordaos. A DataJud
    so retorna metadados processuais: numero, classe, orgao julgador, datas,
    movimentos. Sem texto. Pra RAG semantico use scrapers (PR19/PR20) ou
    curadoria manual.

Quando usar (PR21):
  1. **Validacao anti-alucinacao**: o Claude Gerador pode inventar numeros
     de processo ('TST RR-99999-99/SP'). Antes de aceitar a citacao na minuta
     final, valida via DataJud — se nao existir, descarta ou anota '[citacao
     nao verificada]'.
  2. **Enriquecimento manual**: ao salvar um paradigma na tabela
     `jurisprudencia_externa`, este service preenche classe/orgao_julgador/
     dataAjuizamento automaticamente a partir do numero.

Limite operacional do CNJ: ~120 req/min por API key (publica, compartilhada).
Aplicamos rate limit de 1.0s entre chamadas pra ficar bem abaixo.

Numero CNJ: formato oficial NNNNNNN-DD.AAAA.J.TR.OOOO (20 digitos). A API
busca pelo numero unformatado (sem hifen/ponto). Este service normaliza
automaticamente.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


# API key publica do CNJ DataJud (documentada em datajud-wiki.cnj.jus.br).
# Eh rotacionada pelo CNJ ocasionalmente; se receber 401 sistematico,
# reverificar em https://datajud-wiki.cnj.jus.br/api-publica/acesso/.
DATAJUD_API_KEY_PUBLICA = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

BASE_URL = "https://api-publica.datajud.cnj.jus.br"
RATE_LIMIT_SEC = 1.0
TIMEOUT_SEC = 15

# Mapeamento de sigla-curta -> alias do indice Elasticsearch.
# Lista completa em https://datajud-wiki.cnj.jus.br/api-publica/endpoints
# Focamos nos tribunais com volume trabalhista/civel relevante.
TRIBUNAL_ALIASES: dict[str, str] = {
    "tst": "api_publica_tst",
    "stj": "api_publica_stj",
    "stf": "api_publica_stf",
    "tjpe": "api_publica_tjpe",
    "tjsp": "api_publica_tjsp",
    "tjrj": "api_publica_tjrj",
    "tjmg": "api_publica_tjmg",
    "tjrs": "api_publica_tjrs",
    "trt6": "api_publica_trt6",  # PE/AL
    "trt1": "api_publica_trt1",  # RJ
    "trt2": "api_publica_trt2",  # SP
    "trt3": "api_publica_trt3",  # MG
    "trt4": "api_publica_trt4",  # RS
    "trt15": "api_publica_trt15",  # SP interior
}


class DataJudError(RuntimeError):
    """Falha de comunicacao ou autenticacao com a API DataJud."""


def normalizar_numero_cnj(numero: str) -> str:
    """Remove hifen, ponto e espacos. Resultado deve ter 20 digitos.

    Aceita 'NNNNNNN-DD.AAAA.J.TR.OOOO' ou '00793000920095040018' indiferente.
    Levanta ValueError se nao resultar em 20 digitos.
    """
    digits = re.sub(r"\D", "", numero or "")
    if len(digits) != 20:
        raise ValueError(
            f"Numero CNJ invalido: esperava 20 digitos apos remover formatacao, "
            f"recebi {len(digits)} ({numero!r})"
        )
    return digits


class DataJudClient:
    """Cliente sincrono do Elasticsearch publico do DataJud."""

    def __init__(
        self,
        *,
        api_key: str = DATAJUD_API_KEY_PUBLICA,
        timeout_sec: float = TIMEOUT_SEC,
        rate_limit_sec: float = RATE_LIMIT_SEC,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"APIKey {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "JurisFlowBot/1.0 (+contato@jurisflow.local)",
            }
        )
        self.timeout_sec = timeout_sec
        self.rate_limit_sec = rate_limit_sec
        self._ultimo_request_ts = 0.0

    def _rate_limit(self) -> None:
        agora = time.time()
        delta = agora - self._ultimo_request_ts
        if delta < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - delta)
        self._ultimo_request_ts = time.time()

    def _resolver_alias(self, tribunal: str) -> str:
        sigla = (tribunal or "").lower().strip()
        alias = TRIBUNAL_ALIASES.get(sigla)
        if not alias:
            raise ValueError(
                f"Tribunal '{tribunal}' nao suportado. Conhecidos: "
                f"{sorted(TRIBUNAL_ALIASES.keys())}"
            )
        return alias

    def buscar_por_numero(
        self, numero_processo: str, tribunal: str
    ) -> dict[str, Any] | None:
        """Retorna o documento do processo se existir; None se nao houver hit.

        Usa Elasticsearch `term` query (match exato, case-sensitive) sobre o
        campo `numeroProcesso` no formato 20-digitos sem hifen/ponto. A API
        DataJud NAO indexa o numero formatado, entao normalizar eh obrigatorio.

        Levanta DataJudError em falha HTTP/rede; ValueError em input invalido.
        """
        numero_norm = normalizar_numero_cnj(numero_processo)
        alias = self._resolver_alias(tribunal)
        url = f"{BASE_URL}/{alias}/_search"
        body = {
            "size": 1,
            "query": {"term": {"numeroProcesso": numero_norm}},
        }

        self._rate_limit()
        try:
            resp = self.session.post(url, json=body, timeout=self.timeout_sec)
        except requests.RequestException as err:
            raise DataJudError(f"Falha de rede chamando DataJud: {err}") from err

        if resp.status_code == 401:
            raise DataJudError(
                "DataJud retornou 401 — API key publica pode ter sido rotacionada. "
                "Conferir em https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
            )
        if not resp.ok:
            raise DataJudError(f"DataJud HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None
        return hits[0].get("_source")

    def validar_processo(self, numero_processo: str, tribunal: str) -> dict[str, Any]:
        """Wrapper user-facing: retorna {existe: bool, metadata: dict|None, erro: str|None}.

        Nunca levanta excecao — sempre retorna o dict. Erro de rede ou input
        invalido vem em `erro` pra ser logado/exibido sem derrubar fluxo.
        """
        try:
            doc = self.buscar_por_numero(numero_processo, tribunal)
        except ValueError as err:
            return {"existe": False, "metadata": None, "erro": str(err)}
        except DataJudError as err:
            logger.warning("DataJud indisponivel: %s", err)
            return {"existe": False, "metadata": None, "erro": str(err)}

        if doc is None:
            return {"existe": False, "metadata": None, "erro": None}

        metadata = self._destilar_metadata(doc)
        return {"existe": True, "metadata": metadata, "erro": None}

    @staticmethod
    def _destilar_metadata(doc: dict[str, Any]) -> dict[str, Any]:
        """Extrai os campos relevantes do documento ES bruto.

        DataJud retorna ~50 campos. Pro projeto importam: classe processual,
        tribunal, grau, orgao julgador atual, data de ajuizamento, formato.
        Os movimentos sao guardados como contagem (lista longa demais pra
        ser util fora de auditoria).
        """
        classe = doc.get("classe") or {}
        sistema = doc.get("sistema") or {}
        formato = doc.get("formato") or {}
        movimentos = doc.get("movimentos") or []

        # Orgao julgador atual = ultimo movimento com orgaoJulgador setado
        orgao_atual: str | None = None
        for mov in reversed(movimentos):
            orgao = (mov.get("orgaoJulgador") or {}).get("nome")
            if orgao:
                orgao_atual = orgao
                break

        return {
            "numero_processo": doc.get("numeroProcesso"),
            "tribunal": doc.get("tribunal"),
            "grau": doc.get("grau"),
            "classe_codigo": classe.get("codigo"),
            "classe_nome": classe.get("nome"),
            "sistema": sistema.get("nome"),
            "formato": formato.get("nome"),
            "data_ajuizamento": doc.get("dataAjuizamento"),
            "ultima_atualizacao": doc.get("dataHoraUltimaAtualizacao"),
            "orgao_julgador_atual": orgao_atual,
            "total_movimentos": len(movimentos),
        }
