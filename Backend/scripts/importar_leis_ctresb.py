"""Importa leis e jurisprudencia do repositorio ctresb/leis para a base de legislacao do RAG.

Fonte: https://github.com/ctresb/leis (textos oficiais convertidos para Markdown;
atos oficiais sao de dominio publico — art. 8, I, Lei 9.610/98). O commit fica
fixado em REPO_COMMIT para a importacao ser reproduzivel.

Traz, artigo por artigo, os diplomas que as areas do sistema usam (CF/88 + ADCT,
CLT, CPC, CC, CDC, FGTS, Beneficios da Previdencia, Vale-Transporte, Trabalho
Temporario/Terceirizacao) e as sumulas/OJs do TST, sumulas vinculantes do STF e
sumulas do STJ. Revogados e cancelados ficam de fora. Artigos longos viram partes
(o modelo de embedding so le o comeco do texto).

Por padrao NAO sobrescreve chaves (origem, numero) ja existentes — preserva a
curadoria manual de legislacao_seed.json. Use --sobrescrever para trocar.

Uso (de Backend/, com DATABASE_* do .env da raiz):
    .venv/Scripts/python.exe scripts/importar_leis_ctresb.py --dry-run
    .venv/Scripts/python.exe scripts/importar_leis_ctresb.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPO_COMMIT = "15eb09b618ff08a38c4dfee06a91bd139d093f5d"
RAW = f"https://raw.githubusercontent.com/ctresb/leis/{REPO_COMMIT}/"
TREE_API = f"https://api.github.com/repos/ctresb/leis/git/trees/{REPO_COMMIT}:"

# (origem, caminho no repo, area_juridica — None = vale pra todas as areas)
LEIS = [
    ("CLT", "federal/decretos-lei/1943/del-5452-1943-05-01.md", "trabalhista"),
    ("CPC", "federal/leis-ordinarias/2015/lei-13105-2015-03-16.md", None),
    ("CC", "federal/leis-ordinarias/2002/lei-10406-2002-01-10.md", None),
    ("CDC", "federal/leis-ordinarias/1990/lei-8078-1990-09-11.md", "consumidor"),
    (
        "Lei 8.036/1990",
        "federal/leis-ordinarias/1990/lei-8036-1990-05-11.md",
        "trabalhista",
    ),
    (
        "Lei 8.213/1991",
        "federal/leis-ordinarias/1991/lei-8213-1991-07-24.md",
        "previdenciario",
    ),
    (
        "Lei 7.418/1985",
        "federal/leis-ordinarias/1985/lei-7418-1985-12-16.md",
        "trabalhista",
    ),
    (
        "Lei 6.019/1974",
        "federal/leis-ordinarias/1974/lei-6019-1974-01-03.md",
        "trabalhista",
    ),
]
CONSTITUICAO = "constituicao.md"
# (origem, pasta no repo, prefixo do numero, area_juridica)
JURISPRUDENCIA = [
    ("Sumula TST", "jurisprudencia/tst/sumulas", "Sumula", "trabalhista"),
    ("OJ TST", "jurisprudencia/tst/orientacoes-jurisprudenciais", "OJ", "trabalhista"),
    (
        "Sumula Vinculante STF",
        "jurisprudencia/stf/sumulas-vinculantes",
        "Sumula Vinculante",
        None,
    ),
    ("Sumula STJ", "jurisprudencia/stj/sumulas", "Sumula", None),
]

MAX_CHARS = 1800

_RE_ART = re.compile(
    r"^\*\*Art\.\s*(\d+(?:\.\d{3})*)\s*[ºo°]?\s*(-[A-Z]+)?\s*[ºo°]?\.?\s*\*\*\s*(.*)$"
)
# Anotacao editorial em italico: *(Redacao dada pela Lei ...)* — aceita 1 nivel de parenteses.
_RE_ANOTACAO = re.compile(r"\s*\*\((?:[^()]|\([^()]*\))*\)\*")
_RE_SO_NEGRITO = re.compile(r"^\*\*[^*]+\*\*$")  # TITULO/CAPITULO/SECAO soltos
_ADCT = "# ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"


def _sem_cabecalho(md: str) -> str:
    """Remove o bloco YAML inicial."""
    if md.startswith("---"):
        fim = md.find("\n---", 3)
        if fim != -1:
            return md[fim + 4 :]
    return md


def _campo_yaml(md: str, chave: str) -> str | None:
    m = re.search(rf'^{chave}:\s*"?([^"\n]*)"?\s*$', md, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


def _limpar_linha(linha: str) -> str:
    return _RE_ANOTACAO.sub("", linha).replace("**", "").strip()


def _em_partes(numero: str, texto: str) -> list[tuple[str, str]]:
    if len(texto) <= MAX_CHARS:
        return [(numero, texto)]
    partes, atual = [], ""
    for linha in texto.split("\n"):
        while len(linha) > MAX_CHARS:  # linha sozinha maior que o limite
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(linha[:MAX_CHARS])
            linha = linha[MAX_CHARS:]
        if atual and len(atual) + 1 + len(linha) > MAX_CHARS:
            partes.append(atual)
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        partes.append(atual)
    return [(f"{numero} (parte {i})", p) for i, p in enumerate(partes, start=1)]


def parse_lei(md: str) -> list[tuple[str, str]]:
    """Artigos de uma lei: [(numero, texto)]. Revogados/vetados ficam de fora.

    Numero repetido (ex.: o decreto que aprova a CLT tem seus proprios arts.
    1 e 2) fica com a ULTIMA ocorrencia — o texto consolidado vem depois.
    """
    artigos: dict[str, list[str]] = {}
    atual: str | None = None
    for linha in _sem_cabecalho(md).split("\n"):
        linha = linha.strip()
        m = _RE_ART.match(linha)
        if m:
            atual = f"art. {m.group(1)}{m.group(2) or ''}"
            artigos[atual] = [_limpar_linha(m.group(3))]  # ultima ocorrencia vence
            continue
        if (
            atual is None
            or not linha
            or linha.startswith("#")
            or _RE_SO_NEGRITO.match(linha)
        ):
            continue
        artigos[atual].append(_limpar_linha(linha))

    itens: list[tuple[str, str]] = []
    for numero, linhas in artigos.items():
        texto = "\n".join(l for l in linhas if l).strip()  # noqa: E741
        if not texto or re.match(r"^\(?(Revogad|Vetad|Suprimid)", texto, re.IGNORECASE):
            continue
        itens.extend(_em_partes(numero, texto))
    return itens


def parse_cf(md: str) -> list[tuple[str, str, str]]:
    """CF/88 e ADCT tem numeracao propria: [(origem, numero, texto)]."""
    corpo, _, adct = md.partition(_ADCT)
    itens = [("CF/88", n, t) for n, t in parse_lei(corpo)]
    if adct:
        itens += [("ADCT", n, t) for n, t in parse_lei(adct)]
    return itens


def parse_sumula(md: str) -> tuple[str, str] | None:
    """Sumula/OJ: (numero, texto) ou None se cancelada/revogada."""
    if (_campo_yaml(md, "revogada") or "").lower() == "true":
        return None
    situacao = (_campo_yaml(md, "situacao") or "").upper()
    if "CANCEL" in situacao or "REVOG" in situacao:
        return None
    numero = _campo_yaml(md, "numero")
    corpo = _sem_cabecalho(md)
    if "## Questão" in corpo:  # formato do BNP/CNJ (sumulas vinculantes do STF)
        corpo = corpo.split("## Questão", 1)[1].split("\n## ", 1)[0]
    corpo = re.split(r"^Histórico:", corpo, maxsplit=1, flags=re.MULTILINE)[0]
    corpo = "\n".join(l for l in corpo.split("\n") if not l.startswith("#"))  # noqa: E741
    corpo = re.sub(r"(\w)-\n(\w)", r"\1\2", corpo)  # hifenizacao do PDF
    texto = re.sub(r"\s+", " ", corpo).strip()
    if not numero or not texto:
        return None
    return numero, texto


def _baixar(caminho: str) -> str:
    with urllib.request.urlopen(RAW + caminho, timeout=60) as resp:
        return resp.read().decode("utf-8")


def _listar(pasta: str) -> list[str]:
    req = urllib.request.Request(
        TREE_API + pasta, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        arvore = json.load(resp)["tree"]
    return [
        f"{pasta}/{item['path']}" for item in arvore if item["path"].endswith(".md")
    ]


def coletar() -> list[tuple[str, str, str, str | None]]:
    """[(origem, numero, texto, area_juridica)] de todas as fontes."""
    itens: list[tuple[str, str, str, str | None]] = []
    itens += [(o, n, t, None) for o, n, t in parse_cf(_baixar(CONSTITUICAO))]
    for origem, caminho, area in LEIS:
        itens += [(origem, n, t, area) for n, t in parse_lei(_baixar(caminho))]
    for origem, pasta, prefixo, area in JURISPRUDENCIA:
        arquivos = _listar(pasta)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for md in pool.map(_baixar, arquivos):
                item = parse_sumula(md)
                if item:
                    itens.append((origem, f"{prefixo} {item[0]}", item[1], area))
    return itens


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "--dry-run", action="store_true", help="so baixa e conta; nao grava"
    )
    ap.add_argument(
        "--sobrescrever", action="store_true", help="atualiza chaves ja existentes"
    )
    args = ap.parse_args(argv)

    inicio = time.time()
    itens = coletar()
    print(
        f"Coletados {len(itens)} itens de ctresb/leis@{REPO_COMMIT[:7]} em {time.time() - inicio:.0f}s"
    )
    for origem, n in sorted(Counter(i[0] for i in itens).items()):
        print(f"  {origem}: {n}")
    if args.dry_run:
        for origem, numero, texto, _ in itens[:: max(1, len(itens) // 6)][:6]:
            print(f"  ex.: {origem} {numero}: {texto[:110]!r}")
        return 0

    from App.database import listar_chaves_legislacao, upsert_legislacao_lote
    from App.services.embedding_service import gerar_embeddings_batch

    if not args.sobrescrever:
        existentes = listar_chaves_legislacao()
        antes = len(itens)
        itens = [i for i in itens if (i[0], i[1]) not in existentes]
        print(f"Pulando {antes - len(itens)} ja existentes (curadoria preservada)")

    gravados = 0
    for i in range(0, len(itens), 128):
        lote = itens[i : i + 128]
        embeddings = gerar_embeddings_batch([f"{o} {n} {t}" for o, n, t, _ in lote])
        gravados += upsert_legislacao_lote(
            [(o, n, t, a, e) for (o, n, t, a), e in zip(lote, embeddings)]
        )
        print(f"  {gravados}/{len(itens)} gravados ({time.time() - inicio:.0f}s)")
    print(f"Pronto: {gravados} itens em {time.time() - inicio:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
