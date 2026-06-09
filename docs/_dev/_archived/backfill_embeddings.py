"""Backfill de embeddings semanticos para contestacoes existentes (PR6 #4).

Itera todas as contestacoes com status='ok' que ainda nao tem fatos_embedding,
gera o embedding via embedding_service e salva no banco.

Uso:
    cd Backend
    pip install cohere  # ou openai
    EMBEDDING_PROVIDER=cohere COHERE_API_KEY=xxx python ../docs/_dev/backfill_embeddings.py

Flags:
    --dry-run    : lista quantos registros seriam processados sem chamar a API
    --limit N    : processa no maximo N registros (util para testes)
    --batch N    : tamanho do lote entre commits (default: 10)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Adiciona Backend/ ao path para importar App.*
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "Backend"
sys.path.insert(0, str(BACKEND_DIR))

# Carrega .env do Backend se existir
_env_path = BACKEND_DIR / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from App.database import _get_connection, _ensure_db_initialized, salvar_embedding  # noqa: E402
from App.services.embedding_service import gerar_embedding  # noqa: E402


def _buscar_sem_embedding(limit: int | None = None) -> list[tuple[int, str, str]]:
    """Retorna (id, fatos, pedido_autor) de contestacoes sem embedding."""
    _ensure_db_initialized()
    sql = """
        SELECT id, fatos, pedido_autor
        FROM contestacoes
        WHERE status = 'ok'
          AND fatos_embedding IS NULL
          AND fatos IS NOT NULL
          AND fatos != ''
        ORDER BY id ASC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [(int(r[0]), str(r[1] or ""), str(r[2] or "")) for r in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill embeddings RAG semantico.")
    parser.add_argument("--dry-run", action="store_true", help="Nao chama API, apenas conta.")
    parser.add_argument("--limit", type=int, default=None, help="Max registros a processar.")
    parser.add_argument("--batch", type=int, default=10, help="Lote de commits (default 10).")
    args = parser.parse_args()

    rows = _buscar_sem_embedding(args.limit)
    print(f"Contestacoes sem embedding: {len(rows)}")

    if args.dry_run:
        print("--dry-run: nada foi processado.")
        return

    if not rows:
        print("Nada a fazer.")
        return

    provider = os.getenv("EMBEDDING_PROVIDER", "cohere")
    key_var = "COHERE_API_KEY" if provider == "cohere" else "OPENAI_API_KEY"
    if not os.getenv(key_var):
        print(f"ERRO: {key_var} nao definida. Configure a variavel de ambiente.", file=sys.stderr)
        sys.exit(1)

    ok = 0
    erros = 0
    batch = args.batch or 10

    for i, (contestacao_id, fatos, pedido_autor) in enumerate(rows, 1):
        texto = f"{fatos} {pedido_autor}".strip()
        if not texto:
            print(f"  [{i}/{len(rows)}] id={contestacao_id} — ignorado (texto vazio)")
            continue

        emb = gerar_embedding(texto)
        if emb is None:
            print(f"  [{i}/{len(rows)}] id={contestacao_id} — ERRO: embedding retornou None")
            erros += 1
            continue

        try:
            salvar_embedding(contestacao_id, emb)
            ok += 1
            print(f"  [{i}/{len(rows)}] id={contestacao_id} — OK")
        except Exception as err:
            print(f"  [{i}/{len(rows)}] id={contestacao_id} — ERRO ao salvar: {err}")
            erros += 1

        # Pequeno delay a cada lote para nao estourar rate limit da API
        if i % batch == 0:
            time.sleep(0.5)

    print(f"\nConcluido: {ok} ok, {erros} erros de {len(rows)} registros.")


if __name__ == "__main__":
    main()
