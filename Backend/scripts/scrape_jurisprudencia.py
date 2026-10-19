"""CLI pra coletar jurisprudencia de tribunais e popular public.jurisprudencia_externa.

PR19 Fase 1: suporta STJ. Tribunais adicionais entram em PRs futuros (TJ-PE, TST).

Uso:
    cd Backend
    PYTHONPATH=/app python scripts/scrape_jurisprudencia.py \\
        --tribunal=stj \\
        --query="rescisao indireta" \\
        --area=trabalhista \\
        --max=10

Variantes:
    # Sem area_juridica explicita (classifica por tipo_acao downstream)
    --tribunal=stj --query="adicional insalubridade" --max=5

    # Dry run: nao grava no banco, so mostra o que seria salvo
    --tribunal=stj --query="ferias proporcionais" --max=3 --dry-run

Pre-requisitos:
- Container backend rodando OU venv com DATABASE_URL setado
- EMBEDDING_PROVIDER=local (sentence-transformers, instalado por padrao)
- Acesso a internet pro portal do STJ

LIMITACAO CONHECIDA — Cloudflare Turnstile do STJ em IP de datacenter:
  Smoke real (2026-06-29) confirmou que NEM curl_cffi NEM Playwright
  headless com stealth conseguem passar do Turnstile quando o request vem
  de IP de datacenter (Docker rodando em servidor, AWS, Hetzner, GCP).
  Cloudflare combina reputacao do IP + sinais de automacao mais avancados.

  Como usar este script HOJE:
   * Rode no notebook do dev (IP residencial) com .venv local:
       cd Backend
       .venv\\Scripts\\python.exe scripts/scrape_jurisprudencia.py \\
           --tribunal=stj --query="rescisao indireta" --max=10
   * O scraper tentara curl_cffi primeiro (~1s); se cair (raro em residencial)
     cai pra Playwright (~10-25s). Pro Playwright local, instale Chromium:
       .venv\\Scripts\\python.exe -m playwright install chromium

  Alternativas pra produzir em servidor (PRs futuros):
   - CAPTCHA solver (2Captcha API): ~US$ 2 / 1000 challenges
   - Proxy residencial (BrightData): ~US$ 5/GB
   - Migrar tribunais que nao tem Cloudflare primeiro (TJ-PE, TST)

  Detalhes na docstring do `Backend/App/services/scrapers/stj.py`.

Saida: log estruturado com {capturados, embeddings_gerados, duplicados, falhas}.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Permite rodar de qualquer diretorio dentro de Backend/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from App.database import upsert_jurisprudencia  # noqa: E402
from App.services.embedding_service import gerar_embedding  # noqa: E402
from App.services.scrapers import STJScraper, TSTScraper  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("scrape_jurisprudencia")

SCRAPERS = {
    "stj": STJScraper,
    "tst": TSTScraper,  # PR31 — API REST publica, sem Cloudflare/auth
    # 'tjpe': TJPEScraper,  # futuro
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Coleta jurisprudencia de tribunais e indexa no RAG.",
    )
    parser.add_argument(
        "--tribunal",
        required=True,
        choices=sorted(SCRAPERS.keys()),
        help="Tribunal alvo. Hoje so STJ; TJ-PE e TST em PRs futuros.",
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Termo de busca (ex: 'rescisao indireta', 'adicional insalubridade').",
    )
    parser.add_argument(
        "--area",
        default=None,
        help="Area juridica canonica (trabalhista|consumidor|...). Opcional.",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="Max acordaos por execucao. Cap rigido em 50 (alem disso o portal "
        "bloqueia com captcha).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao grava no banco, so mostra o que seria salvo.",
    )
    parser.add_argument(
        "--cookies",
        default=None,
        help="Path pra JSON de cookies pre-autenticados (workflow anti-Cloudflare "
        "Turnstile). Exportar via `scripts/exportar_cookies_stj.py`.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    scraper_cls = SCRAPERS[args.tribunal]
    # PR27 (finding #13): probe se o scraper aceita cookies_path. STJ aceita
    # (PR26); tribunais futuros (TJ-PE, TST) podem nao aceitar. Verificacao
    # dinamica em vez de TypeError silencioso.
    import inspect

    scraper_kwargs: dict = {}
    if args.cookies:
        sig = inspect.signature(scraper_cls.__init__)
        if "cookies_path" in sig.parameters:
            scraper_kwargs["cookies_path"] = args.cookies
        else:
            logger.warning(
                "Scraper %s nao aceita --cookies (nao tem cookies_path no __init__). "
                "Ignorando flag.",
                args.tribunal,
            )
    scraper = scraper_cls(**scraper_kwargs)

    inicio = time.time()
    logger.info(
        "Iniciando coleta tribunal=%s query=%r max=%d dry=%s",
        args.tribunal,
        args.query,
        args.max,
        args.dry_run,
    )

    try:
        acordaos = scraper.buscar(args.query, max_resultados=args.max)
    except Exception as err:
        logger.error("Scraper falhou: %s", err)
        return 1

    if not acordaos:
        logger.warning("Nenhum acordao retornado. Tente outra query ou aguarde.")
        return 0

    logger.info("Coletados %d acordaos. Gerando embeddings...", len(acordaos))

    capturados = 0
    embeddings_gerados = 0
    falhas = 0

    for i, ac in enumerate(acordaos, start=1):
        try:
            # Texto pra embedding combina ementa + tese_firmada (quando houver)
            texto_embed = ac["ementa"]
            if ac.get("tese_firmada"):
                texto_embed = f"{ac['tese_firmada']}\n\n{texto_embed}"

            embedding = gerar_embedding(texto_embed[:5000])  # cap defensivo
            if embedding:
                embeddings_gerados += 1
            else:
                logger.warning(
                    "[%d/%d] %s sem embedding (provider local indisponivel?)",
                    i,
                    len(acordaos),
                    ac["numero_processo"],
                )

            if args.dry_run:
                logger.info(
                    "[DRY] %s | %s | data=%s | ementa=%d chars",
                    ac["numero_processo"],
                    ac["tipo_decisao"],
                    ac.get("data_julgamento", "?"),
                    len(ac["ementa"]),
                )
            else:
                upsert_jurisprudencia(
                    tribunal=ac["tribunal"],
                    numero_processo=ac["numero_processo"],
                    ementa=ac["ementa"],
                    tipo_decisao=ac.get("tipo_decisao", "Acordao"),
                    relator=ac.get("relator"),
                    data_julgamento=ac.get("data_julgamento"),
                    tese_firmada=ac.get("tese_firmada"),
                    area_juridica=args.area,
                    peso_relevancia=ac.get("peso_relevancia_sugerido", 5),
                    fonte_url=ac.get("fonte_url"),
                    embedding=embedding,
                )
            capturados += 1
        except Exception as err:  # noqa: BLE001 — falha de um nao trava lote
            falhas += 1
            logger.error(
                "[%d/%d] Falha no upsert de %s: %s",
                i,
                len(acordaos),
                ac.get("numero_processo", "?"),
                err,
            )

    duracao = time.time() - inicio
    logger.info(
        "Concluido em %.1fs | capturados=%d embeddings=%d falhas=%d dry=%s",
        duracao,
        capturados,
        embeddings_gerados,
        falhas,
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
