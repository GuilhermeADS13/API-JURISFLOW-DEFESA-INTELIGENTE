"""Servico de ingestao em lote de jurisprudencia por FONTE (PR34).

Centraliza a logica de coleta + embedding + upsert usada por:
  - `scripts/scrape_jurisprudencia_lote.py` (CLI manual)
  - `POST /api/admin/jurisprudencia/scrape` (agendamento via n8n Schedule)

Fontes (todas com API publica JSON, sem Cloudflare nem auth — rodam em cron):
  - tst  -> TSTScraper  (API REST do TST)  -> area trabalhista (~360k acordaos)
  - carf -> CARFScraper (Solr do CARF)     -> area tributaria  (~580k acordaos)

O STJ (que cobriria tributario no judiciario) fica de fora: Cloudflare Turnstile
bloqueia IP de datacenter. O CARF (tributario administrativo) e a fonte limpa.

Etica/anti-abuso: cada scraper aplica rate limit 1.5s e User-Agent identificado.
Jurisprudencia e publica (art. 93, IX, CF).
"""

from __future__ import annotations

import logging
import time

from App.services.scrapers import CARFScraper, TSTScraper

logger = logging.getLogger(__name__)

# Temas trabalhistas: controversias mais comuns em contestacoes trabalhistas.
TEMAS_TRABALHISTA = [
    "horas extras intervalo intrajornada",
    "adicional de insalubridade",
    "adicional de periculosidade",
    "dano moral trabalhista",
    "assedio moral",
    "reconhecimento de vinculo empregaticio",
    "equiparacao salarial",
    "rescisao indireta",
    "estabilidade gestante",
    "terceirizacao responsabilidade subsidiaria",
    "grupo economico responsabilidade solidaria",
    "reversao de justa causa",
    "adicional noturno",
    "acumulo de funcao",
    "doenca ocupacional acidente de trabalho",
    "FGTS multa de quarenta por cento",
]

# Temas tributarios: controversias mais comuns em contencioso tributario (CARF).
TEMAS_TRIBUTARIO = [
    "PIS COFINS creditamento insumos",
    "exclusao ICMS base calculo PIS COFINS",
    "IRPJ CSLL adicao base de calculo",
    "compensacao tributaria homologacao",
    "decadencia lancamento tributario",
    "multa qualificada dolo fraude",
    "planejamento tributario abusivo simulacao",
    "amortizacao de agio rentabilidade futura",
    "denuncia espontanea multa moratoria",
    "responsabilidade tributaria solidaria",
    "IPI credito presumido ressarcimento",
    "preco de transferencia",
    "juros selic repeticao de indebito",
    "ISS local da prestacao de servico",
]

FONTES = {
    "tst": {"scraper": TSTScraper, "area": "trabalhista", "temas": TEMAS_TRABALHISTA},
    "carf": {"scraper": CARFScraper, "area": "tributario", "temas": TEMAS_TRIBUTARIO},
}


def ingerir_lote(
    fonte: str,
    temas: list[str] | None = None,
    *,
    max_por_tema: int = 4,
    dry_run: bool = False,
) -> dict:
    """Roda o scraper da `fonte` por tema e faz upsert no RAG. Retorna stats.

    Dedup por (tribunal, numero_processo) em memoria evita reembeddar o mesmo
    acordao que aparece em >1 tema. O upsert no banco tambem e idempotente.

    Import tardio de `upsert_jurisprudencia`/`gerar_embedding` mantem o modulo
    barato de importar (nao inicializa pool de DB nem carrega modelo no import).
    """
    from App.database import upsert_jurisprudencia
    from App.services.embedding_service import gerar_embedding

    if fonte not in FONTES:
        raise ValueError(f"fonte invalida: {fonte!r} (use {sorted(FONTES)})")
    cfg = FONTES[fonte]
    area = cfg["area"]
    temas = temas or cfg["temas"]
    scraper = cfg["scraper"]()
    inicio = time.time()

    vistos: set[str] = set()
    capturados = embeddings_gerados = duplicados = falhas = 0
    por_tema: dict[str, int] = {}

    for tema in temas:
        try:
            acordaos = scraper.buscar(tema, max_resultados=max_por_tema)
        except Exception as err:  # noqa: BLE001 — nao trava o lote
            logger.error("[%s] tema=%r falhou na busca: %s", fonte, tema, err)
            por_tema[tema] = 0
            continue

        novos_tema = 0
        for ac in acordaos:
            numero = ac.get("numero_processo")
            if not numero:
                continue
            chave = f"{ac.get('tribunal')}::{numero}"
            if chave in vistos:
                duplicados += 1
                continue
            vistos.add(chave)

            try:
                texto_embed = ac["ementa"]
                if ac.get("tese_firmada"):
                    texto_embed = f"{ac['tese_firmada']}\n\n{texto_embed}"
                embedding = gerar_embedding(texto_embed[:5000])
                if embedding:
                    embeddings_gerados += 1

                if not dry_run:
                    upsert_jurisprudencia(
                        tribunal=ac["tribunal"],
                        numero_processo=numero,
                        ementa=ac["ementa"],
                        tipo_decisao=ac.get("tipo_decisao", "Acordao"),
                        relator=ac.get("relator"),
                        data_julgamento=ac.get("data_julgamento"),
                        tese_firmada=ac.get("tese_firmada"),
                        area_juridica=area,
                        peso_relevancia=ac.get("peso_relevancia_sugerido", 5),
                        fonte_url=ac.get("fonte_url"),
                        embedding=embedding,
                    )
                capturados += 1
                novos_tema += 1
            except Exception as err:  # noqa: BLE001
                falhas += 1
                logger.error("[%s] upsert falhou p/ %s: %s", fonte, numero, err)

        por_tema[tema] = novos_tema
        logger.info(
            "[%s] tema=%r -> %d novos (retornou %d)",
            fonte,
            tema,
            novos_tema,
            len(acordaos),
        )

    stats = {
        "fonte": fonte,
        "area": area,
        "temas": len(temas),
        "capturados": capturados,
        "embeddings_gerados": embeddings_gerados,
        "duplicados_intra_lote": duplicados,
        "falhas": falhas,
        "duracao_s": round(time.time() - inicio, 1),
        "dry_run": dry_run,
        "por_tema": por_tema,
    }
    logger.info("[%s] LOTE concluido: %s", fonte, stats)
    return stats
