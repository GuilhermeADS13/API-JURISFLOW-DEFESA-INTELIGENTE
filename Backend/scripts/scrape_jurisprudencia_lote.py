"""CLI fino de ingestao em lote de jurisprudencia. A logica vive no service
`App.services.jurisprudencia_ingest` (reusado tambem pelo endpoint de
agendamento POST /api/admin/jurisprudencia/scrape).

Uso (dentro do container backend, que tem DATABASE_URL + modelo de embedding):
    docker exec autojuri_backend python scripts/scrape_jurisprudencia_lote.py --fonte=tst
    docker exec autojuri_backend python scripts/scrape_jurisprudencia_lote.py --fonte=carf --max-por-tema=4
    docker exec autojuri_backend python scripts/scrape_jurisprudencia_lote.py --fonte=carf --dry-run
    docker exec autojuri_backend python scripts/scrape_jurisprudencia_lote.py --fonte=todas
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from App.services.jurisprudencia_ingest import FONTES, ingerir_lote  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingestao em lote de jurisprudencia por fonte."
    )
    p.add_argument(
        "--fonte",
        default="tst",
        choices=[*sorted(FONTES), "todas"],
        help="Fonte: tst (trabalhista), carf (tributario) ou todas.",
    )
    p.add_argument(
        "--max-por-tema", type=int, default=4, help="Max acordaos por tema (default 4)."
    )
    p.add_argument(
        "--temas",
        default=None,
        help="Lista de temas separada por virgula (sobrescreve a curada).",
    )
    p.add_argument("--dry-run", action="store_true", help="Nao grava no banco.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    temas = [t.strip() for t in args.temas.split(",")] if args.temas else None
    fontes = sorted(FONTES) if args.fonte == "todas" else [args.fonte]
    falhas_total = 0
    for f in fontes:
        stats = ingerir_lote(
            f,
            temas if args.fonte != "todas" else None,
            max_por_tema=args.max_por_tema,
            dry_run=args.dry_run,
        )
        falhas_total += stats["falhas"]
    return 0 if falhas_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
