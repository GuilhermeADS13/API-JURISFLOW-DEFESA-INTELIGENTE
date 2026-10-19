"""Ingere dataset seed de jurisprudencia paradigma em public.jurisprudencia_externa (PR22).

Le `Backend/data/jurisprudencia_seed.json`, gera embedding por entrada via
sentence-transformers (provider=local, 384 dims) e faz UPSERT por
(tribunal, numero_processo). Idempotente — pode rodar varias vezes sem duplicar.

Pra que serve: popular a tabela `jurisprudencia_externa` SEM depender de scraping
dos portais (STJ/TJ-PE bloqueados por Cloudflare em datacenter — vide PR20/PR21).
Os 30 acordaos paradigma trabalhistas curados manualmente cobrem os temas
recorrentes do app: rescisao indireta, justa causa, horas extras, equiparacao
salarial, insalubridade, FGTS, dano moral, estabilidade, vinculo, prescricao,
sucessao, justica gratuita.

Uso:
    cd Backend
    ./.venv/Scripts/python.exe scripts/ingest_seed_jurisprudencia.py

Pre-requisito: backend container UP (ou venv com EMBEDDING_PROVIDER=local +
sentence-transformers instalado) + acesso ao Supabase via DATABASE_URL.

Saida: contagem por tribunal + duracao total + numero de embeddings gerados.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Permite rodar de qualquer diretorio dentro de Backend/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from App.database import upsert_jurisprudencia  # noqa: E402
from App.services.embedding_service import gerar_embedding  # noqa: E402


CAMPOS_OBRIGATORIOS = ("tribunal", "numero_processo", "ementa")


def main() -> int:
    seed_path = ROOT / "data" / "jurisprudencia_seed.json"
    if not seed_path.exists():
        print(f"ERRO: dataset nao encontrado em {seed_path}", file=sys.stderr)
        return 1

    try:
        entries = json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        print(f"ERRO: JSON invalido em {seed_path}: {err}", file=sys.stderr)
        return 1

    if not isinstance(entries, list):
        print("ERRO: dataset deve ser uma lista JSON", file=sys.stderr)
        return 1

    print(f"Ingerindo {len(entries)} entradas de {seed_path.name}...")
    inicio = time.time()
    por_tribunal: dict[str, int] = {}
    embeddings_gerados = 0
    sem_embedding = 0
    falhas = 0

    for i, entry in enumerate(entries, start=1):
        # Valida campos obrigatorios — sem eles o upsert nem chega a tentar
        faltando = [
            c for c in CAMPOS_OBRIGATORIOS if not str(entry.get(c) or "").strip()
        ]
        if faltando:
            print(
                f"  [{i}/{len(entries)}] SKIP — campos faltando {faltando}: "
                f"{entry.get('numero_processo') or '?'}"
            )
            falhas += 1
            continue

        tribunal = str(entry["tribunal"]).strip()
        numero = str(entry["numero_processo"]).strip()
        ementa = str(entry["ementa"]).strip()

        # Embedding sobre numero + tese (se houver) + ementa — mesmo conteudo
        # que entra no tsvector da tabela.
        tese = str(entry.get("tese_firmada") or "").strip()
        texto_pra_embed = f"{numero} {tese} {ementa}".strip()
        embedding = gerar_embedding(texto_pra_embed)
        if embedding is None:
            sem_embedding += 1
            print(
                f"  [{i}/{len(entries)}] AVISO — sem embedding pra {tribunal} {numero} "
                "(provider local indisponivel?)"
            )
        else:
            embeddings_gerados += 1

        try:
            upsert_jurisprudencia(
                tribunal=tribunal,
                numero_processo=numero,
                ementa=ementa,
                tipo_decisao=str(entry.get("tipo_decisao") or "Acordao"),
                relator=entry.get("relator"),
                data_julgamento=entry.get("data_julgamento"),
                tese_firmada=entry.get("tese_firmada"),
                area_juridica=entry.get("area_juridica"),
                peso_relevancia=int(entry.get("peso_relevancia") or 5),
                fonte_url=entry.get("fonte_url"),
                embedding=embedding,
            )
            por_tribunal[tribunal] = por_tribunal.get(tribunal, 0) + 1
        except Exception as err:  # noqa: BLE001 — falha de um nao trava o lote
            falhas += 1
            print(f"  [{i}/{len(entries)}] FALHA upsert {tribunal} {numero}: {err}")
            continue

        if i % 10 == 0:
            print(f"  [{i}/{len(entries)}] processado, {time.time() - inicio:.1f}s")

    duracao = time.time() - inicio
    print()
    print(f"Concluido em {duracao:.1f}s.")
    print(f"Por tribunal: {dict(sorted(por_tribunal.items()))}")
    print(f"Embeddings gerados: {embeddings_gerados}/{len(entries)}")
    if sem_embedding:
        print(
            f"AVISO: {sem_embedding} entradas sem embedding — "
            "busca semantica nao retornara essas"
        )
    if falhas:
        print(f"FALHAS: {falhas} entradas nao ingeridas")
        return 1 if falhas == len(entries) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
