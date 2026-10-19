"""Importa JSON de scraping externo em `public.jurisprudencia_externa` (PR25).

Reescrita do `integrar_json_supabase.py` proposto no `GUIA_EXPANSAO_SCRAPER.md`,
alinhada com o codigo real do projeto:

- Usa `upsert_jurisprudencia` (helper canonico com validacao + UPSERT
  idempotente por (tribunal, numero_processo) + pgvector formatado).
- Respeita cap de 512 tokens do modelo local sentence-transformers.
- Se `ementa` nao vier no JSON, destila via Claude Haiku 4.5 (barato,
  ~US$0.001 por acordao — resolve o "problema #5" do script original que
  usava `conteudo[:500]` como ementa).
- Aceita `numero_processo` explicito no JSON (recomendado). So faz regex
  CNJ como fallback quando ausente. Nao usa `hash()` do Python (nao-
  deterministico).

Uso:
    cd Backend
    ./.venv/Scripts/python.exe scripts/importar_jurisprudencia_json.py \\
        --input=path/pra/extracao.json --dry-run

Formato esperado do JSON de entrada (lista de objetos):
    [
      {
        "tribunal": "TRF5",
        "numero_processo": "0001234-56.2023.4.05.8300",   // opcional
        "ementa": "APELACAO CIVEL. ...",                    // opcional
        "conteudo": "acordao completo aqui...",             // vira texto_integral
        "relator": "Des. Fulano",                           // opcional
        "data_julgamento": "2023-05-10",                    // opcional ISO
        "area_juridica": "trabalhista",                     // opcional
        "peso_relevancia": 5,                               // opcional 1-10
        "fonte_url": "https://..."                          // opcional
      },
      ...
    ]

Se `numero_processo` faltar, tenta regex CNJ em `conteudo`. Se nao achar,
skip com log warning.

Se `ementa` faltar, chama Haiku pra destilar `conteudo`. Requer
`ANTHROPIC_API_KEY` no env; senao skip e log warning.

Exit codes: 0 sucesso, 1 arquivo nao encontrado / JSON invalido.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

# Permite rodar de qualquer diretorio dentro de Backend/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from App.database import upsert_jurisprudencia  # noqa: E402
from App.services.embedding_service import (  # noqa: E402
    gerar_embedding,
    gerar_embeddings_batch,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("importar_jurisprudencia_json")


# CNJ: 20 digitos formato NNNNNNN-DD.AAAA.J.TR.OOOO
_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

# Haiku eh 5-10x mais barato que Sonnet — perfeito pra destilacao de ementa
_HAIKU_MODEL_DEFAULT = "claude-haiku-4-5"
_HAIKU_MAX_TOKENS = 600  # ementa cabe folgado
_HAIKU_TIMEOUT_SEC = 30


def _extrair_cnj(texto: str) -> str | None:
    m = _CNJ_RE.search(texto or "")
    return m.group(0) if m else None


def _destilar_ementa_via_haiku(
    conteudo: str, *, api_key: str, model: str = _HAIKU_MODEL_DEFAULT
) -> str | None:
    """Chama Claude Haiku pra extrair a ementa do texto integral.

    Retorna None em erro — chamador decide pular ou nao.
    """
    if not api_key or not conteudo:
        return None
    prompt = (
        "Voce eh assistente juridico. A partir do texto abaixo (acordao ou "
        "sentenca), extraia APENAS a EMENTA — o resumo formal em maiusculas "
        "no inicio do acordao. Se nao houver ementa clara, sintetize em 3-5 "
        "linhas o dispositivo principal + fundamento nuclear. NAO cite artigos "
        "ou jurisprudencia — so a essencia decisoria. Retorne texto puro, sem "
        "aspas, sem markdown, sem prefixo tipo 'Ementa:'.\n\n"
        f"TEXTO:\n{conteudo[:12000]}"  # cap defensivo
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": _HAIKU_MAX_TOKENS,
                "temperature": 0.0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_HAIKU_TIMEOUT_SEC,
        )
    except requests.RequestException as err:
        logger.warning("Haiku falhou: %s", err)
        return None
    if not resp.ok:
        logger.warning("Haiku HTTP %d: %s", resp.status_code, resp.text[:200])
        return None
    payload = resp.json()
    blocks = payload.get("content") or []
    texto = "".join(
        b.get("text", "") for b in blocks if b.get("type") == "text"
    ).strip()
    return texto or None


def _preparar_entrada(
    entry: dict[str, Any],
    *,
    indice: int,
    total: int,
    api_key: str | None,
) -> tuple[dict, str, str, int, str] | None:
    """Valida + destila entrada. Retorna (entry, ementa, numero, peso, conteudo)
    pronta pra embedding+upsert, ou None se skip.

    Extraida do `_processar_entrada` (PR27 finding #7) pra permitir batch
    encode. `main()` chama `_preparar_entrada` primeiro pra todas as entradas,
    depois faz batch de embeddings, depois upsert.
    """
    tribunal = str(entry.get("tribunal") or "").strip()
    numero = str(entry.get("numero_processo") or "").strip()
    conteudo = str(entry.get("conteudo") or "").strip()
    ementa = str(entry.get("ementa") or "").strip()

    if not tribunal:
        logger.warning("[%d/%d] SKIP — sem 'tribunal'", indice, total)
        return None

    if not numero:
        numero = _extrair_cnj(conteudo) or _extrair_cnj(ementa) or ""
    if not numero:
        logger.warning(
            "[%d/%d] SKIP — sem 'numero_processo' explicito e sem CNJ "
            "detectavel (tribunal=%s)",
            indice,
            total,
            tribunal,
        )
        return None

    if not ementa and conteudo:
        if not api_key:
            logger.warning(
                "[%d/%d] SKIP — sem 'ementa' e ANTHROPIC_API_KEY nao setada "
                "(tribunal=%s numero=%s)",
                indice,
                total,
                tribunal,
                numero,
            )
            return None
        logger.info(
            "[%d/%d] destilando ementa via Haiku (tribunal=%s numero=%s)",
            indice,
            total,
            tribunal,
            numero,
        )
        ementa = _destilar_ementa_via_haiku(conteudo, api_key=api_key) or ""
        if not ementa:
            logger.warning(
                "[%d/%d] SKIP — Haiku nao retornou ementa",
                indice,
                total,
            )
            return None

    if not ementa:
        logger.warning(
            "[%d/%d] SKIP — sem 'ementa' nem 'conteudo' pra destilar",
            indice,
            total,
        )
        return None

    peso_raw = entry.get("peso_relevancia")
    if peso_raw is None or peso_raw == "":
        peso = 5
    else:
        try:
            peso = int(peso_raw)
        except (TypeError, ValueError):
            logger.warning(
                "[%d/%d] SKIP — peso_relevancia invalido %r (%s %s)",
                indice,
                total,
                peso_raw,
                tribunal,
                numero,
            )
            return None
    if peso < 1 or peso > 10:
        logger.warning(
            "[%d/%d] SKIP — peso_relevancia fora de 1-10: %d (%s %s)",
            indice,
            total,
            peso,
            tribunal,
            numero,
        )
        return None

    return (entry, ementa, numero, peso, conteudo)


def _processar_entrada(
    entry: dict[str, Any],
    *,
    indice: int,
    total: int,
    api_key: str | None,
    dry_run: bool,
) -> str:
    """Legacy shim pra testes existentes. Retorna 'ok' | 'skip' | 'falha'.

    O `main()` agora usa `_preparar_entrada` + batch. Esta funcao mantem o
    fluxo antigo (individual encode) pra nao quebrar `test_processar_entrada*`.
    """
    tribunal = str(entry.get("tribunal") or "").strip()
    numero = str(entry.get("numero_processo") or "").strip()
    conteudo = str(entry.get("conteudo") or "").strip()
    ementa = str(entry.get("ementa") or "").strip()

    if not tribunal:
        logger.warning("[%d/%d] SKIP — sem 'tribunal'", indice, total)
        return "skip"

    # Fallback pra numero: regex CNJ em conteudo/ementa
    if not numero:
        numero = _extrair_cnj(conteudo) or _extrair_cnj(ementa) or ""
    if not numero:
        logger.warning(
            "[%d/%d] SKIP — sem 'numero_processo' explicito e sem CNJ "
            "detectavel em 'conteudo'/'ementa' (tribunal=%s)",
            indice,
            total,
            tribunal,
        )
        return "skip"

    # Se ementa nao veio no JSON, destila via Haiku
    if not ementa and conteudo:
        if not api_key:
            logger.warning(
                "[%d/%d] SKIP — sem 'ementa' no JSON e ANTHROPIC_API_KEY nao setada "
                "(tribunal=%s numero=%s)",
                indice,
                total,
                tribunal,
                numero,
            )
            return "skip"
        logger.info(
            "[%d/%d] destilando ementa via Haiku (tribunal=%s numero=%s)",
            indice,
            total,
            tribunal,
            numero,
        )
        ementa = _destilar_ementa_via_haiku(conteudo, api_key=api_key) or ""
        if not ementa:
            logger.warning(
                "[%d/%d] SKIP — Haiku nao retornou ementa",
                indice,
                total,
            )
            return "skip"

    if not ementa:
        logger.warning(
            "[%d/%d] SKIP — sem 'ementa' nem 'conteudo' pra destilar",
            indice,
            total,
        )
        return "skip"

    # Embedding sobre a ementa (que cabe em 512 tokens tranquilo)
    embedding = gerar_embedding(ementa)
    if embedding is None:
        logger.warning(
            "[%d/%d] AVISO — sem embedding gerado (%s %s)",
            indice,
            total,
            tribunal,
            numero,
        )

    # PR27 (finding #12): validar peso_relevancia ANTES do upsert com mensagem
    # especifica. Antes: int('alto') levantava ValueError capturado pelo
    # `except Exception` mais abaixo, gerando log 'FALHA upsert' enganoso.
    peso_raw = entry.get("peso_relevancia")
    if peso_raw is None or peso_raw == "":
        peso = 5
    else:
        try:
            peso = int(peso_raw)
        except (TypeError, ValueError):
            logger.warning(
                "[%d/%d] SKIP — peso_relevancia invalido %r (%s %s)",
                indice,
                total,
                peso_raw,
                tribunal,
                numero,
            )
            return "skip"
    if peso < 1 or peso > 10:
        logger.warning(
            "[%d/%d] SKIP — peso_relevancia fora de 1-10: %d (%s %s)",
            indice,
            total,
            peso,
            tribunal,
            numero,
        )
        return "skip"

    if dry_run:
        logger.info(
            "[DRY %d/%d] %s | %s | ementa=%d chars | texto_integral=%d chars | emb=%s",
            indice,
            total,
            tribunal,
            numero,
            len(ementa),
            len(conteudo),
            embedding is not None,
        )
        return "ok"

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
            peso_relevancia=peso,
            fonte_url=entry.get("fonte_url"),
            embedding=embedding,
            texto_integral=conteudo or None,
        )
    except Exception as err:  # noqa: BLE001 — falha de um nao trava o lote
        logger.error(
            "[%d/%d] FALHA upsert %s %s: %s",
            indice,
            total,
            tribunal,
            numero,
            err,
        )
        return "falha"

    logger.info("[%d/%d] OK %s %s", indice, total, tribunal, numero)
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa JSON de scraping externo em jurisprudencia_externa.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path do JSON de entrada (lista de objetos).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao grava no banco, so simula.",
    )
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        logger.error("Arquivo nao encontrado: %s", path)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        logger.error("JSON invalido em %s: %s", path, err)
        return 1

    if not isinstance(data, list):
        logger.error("JSON deve ser uma lista de objetos, recebi %s", type(data))
        return 1

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY nao setada — entradas sem 'ementa' serao PULADAS"
        )

    logger.info(
        "Importando %d entradas de %s (dry=%s)...",
        len(data),
        path.name,
        args.dry_run,
    )
    inicio = time.time()
    por_tribunal: dict[str, int] = {}
    skips = 0
    falhas = 0

    # PR27 (finding #7): batch encode. Pre-processa (skips + destilacao Haiku)
    # de todas entradas primeiro pra coletar ementas prontas, gera embeddings
    # em UMA chamada model.encode(list, batch_size=32), depois upsert com
    # embedding correspondente. Escala 10x melhor pra >20 entradas.
    # Fallback: entradas com falha na destilacao viram skip antes do batch.

    # Pass 1: validar + destilar. Retorna lista de tuplas (entry, ementa,
    # numero, peso, conteudo) prontas pra upsert, ou None se skip.
    entries_prontos: list[tuple[dict, str, str, int, str] | None] = []
    for i, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            logger.warning("[%d/%d] SKIP — entrada nao e dict", i, len(data))
            skips += 1
            entries_prontos.append(None)
            continue
        preparado = _preparar_entrada(
            entry,
            indice=i,
            total=len(data),
            api_key=api_key,
        )
        entries_prontos.append(preparado)
        if preparado is None:
            skips += 1

    # Pass 2: batch encode das ementas validadas
    textos_pra_embed = [
        f"{tup[2]} {tup[1]}".strip() for tup in entries_prontos if tup is not None
    ]
    if textos_pra_embed:
        logger.info("Gerando %d embeddings em batch...", len(textos_pra_embed))
        embeddings_batch = gerar_embeddings_batch(textos_pra_embed)
    else:
        embeddings_batch = []
    embeddings_iter = iter(embeddings_batch)

    # Pass 3: upsert (ou dry-run) com embedding correspondente
    for i, (entry, tup) in enumerate(zip(data, entries_prontos), start=1):
        if tup is None:
            continue  # ja contado em skips na Pass 1
        _entry_ref, ementa, numero, peso, conteudo = tup
        embedding = next(embeddings_iter, None)
        if embedding is None:
            logger.warning(
                "[%d/%d] AVISO — sem embedding pra %s (batch falhou)",
                i,
                len(data),
                numero,
            )

        tribunal = str(entry.get("tribunal") or "").strip()
        if args.dry_run:
            logger.info(
                "[DRY %d/%d] %s | %s | ementa=%d chars | texto_integral=%d chars | emb=%s",
                i,
                len(data),
                tribunal,
                numero,
                len(ementa),
                len(conteudo),
                embedding is not None,
            )
            por_tribunal[tribunal] = por_tribunal.get(tribunal, 0) + 1
            continue

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
                peso_relevancia=peso,
                fonte_url=entry.get("fonte_url"),
                embedding=embedding,
                texto_integral=conteudo or None,
            )
            por_tribunal[tribunal] = por_tribunal.get(tribunal, 0) + 1
            logger.info("[%d/%d] OK %s %s", i, len(data), tribunal, numero)
        except Exception as err:  # noqa: BLE001 — falha de um nao trava lote
            falhas += 1
            logger.error(
                "[%d/%d] FALHA upsert %s %s: %s",
                i,
                len(data),
                tribunal,
                numero,
                err,
            )

    duracao = time.time() - inicio
    logger.info(
        "Concluido em %.1fs. Por tribunal: %s | skips=%d falhas=%d dry=%s",
        duracao,
        dict(sorted(por_tribunal.items())),
        skips,
        falhas,
        args.dry_run,
    )
    # 1 se TUDO falhou; senao 0 (parciais nao sao erro fatal)
    return (
        1 if not por_tribunal and (skips + falhas) == len(data) and len(data) > 0 else 0
    )


if __name__ == "__main__":
    sys.exit(main())
