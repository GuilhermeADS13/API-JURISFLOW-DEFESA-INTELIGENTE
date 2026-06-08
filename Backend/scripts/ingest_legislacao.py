"""Ingere dataset seed de legislacao em public.legislacao (PR13 #B3).

Le `Backend/data/legislacao_seed.json`, gera embedding por entrada via
sentence-transformers (provider=local, 384 dims) e faz UPSERT por
(origem, numero). Idempotente — pode rodar varias vezes sem duplicar.

Uso:
    cd Backend
    ./.venv/Scripts/python.exe scripts/ingest_legislacao.py

Pre-requisito: backend container UP (ou venv com EMBEDDING_PROVIDER=local +
sentence-transformers instalado) + acesso ao Supabase via DATABASE_URL.

Saida: contagem por origem + tempo total.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Permite rodar de qualquer diretorio dentro de Backend/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from App.database import upsert_legislacao  # noqa: E402
from App.services.embedding_service import gerar_embedding  # noqa: E402


def main() -> int:
    seed_path = ROOT / "data" / "legislacao_seed.json"
    if not seed_path.exists():
        print(f"ERRO: dataset nao encontrado em {seed_path}", file=sys.stderr)
        return 1

    entries = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        print("ERRO: dataset deve ser uma lista JSON", file=sys.stderr)
        return 1

    print(f"Ingerindo {len(entries)} entradas de {seed_path.name}...")
    inicio = time.time()
    por_origem: dict[str, int] = {}
    sem_embedding = 0

    for i, entry in enumerate(entries, start=1):
        origem = str(entry.get("origem") or "").strip()
        numero = str(entry.get("numero") or "").strip()
        texto = str(entry.get("texto") or "").strip()
        area = entry.get("area_juridica")

        if not origem or not numero or not texto:
            print(f"  [{i}/{len(entries)}] SKIP — entrada incompleta: {entry}")
            continue

        # Gera embedding sobre numero + texto (o que aparece no tsvector tambem).
        texto_pra_embed = f"{numero} {texto}"
        embedding = gerar_embedding(texto_pra_embed)
        if embedding is None:
            sem_embedding += 1
            print(
                f"  [{i}/{len(entries)}] AVISO — sem embedding pra {origem} {numero} "
                "(provider local indisponivel?)"
            )

        upsert_legislacao(
            origem=origem,
            numero=numero,
            texto=texto,
            area_juridica=area,
            embedding=embedding,
        )
        por_origem[origem] = por_origem.get(origem, 0) + 1
        if i % 10 == 0:
            print(f"  [{i}/{len(entries)}] processado, {time.time() - inicio:.1f}s")

    duracao = time.time() - inicio
    print()
    print(f"Concluido em {duracao:.1f}s.")
    print("Por origem:")
    for origem in sorted(por_origem):
        print(f"  {origem}: {por_origem[origem]}")
    if sem_embedding:
        print(f"AVISO: {sem_embedding} entradas sem embedding — busca semantica nao retornara essas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
