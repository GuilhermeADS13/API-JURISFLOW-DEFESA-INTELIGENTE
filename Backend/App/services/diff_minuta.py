"""Calcula diff entre minuta original (IA) e minuta editada (humano).

Usado para o golden dataset (PR5 Observabilidade): cada par
{minuta_original, minuta_editada} se torna dado de treino para refinar
prompts ou fazer fine-tuning futuro.

Implementacao usa apenas `difflib` da stdlib — sem dependencias.
"""

from __future__ import annotations

import difflib
from typing import Any

# Secoes da minuta que sao comparadas. Manter alinhado com as chaves que o
# Claude Gerador retorna (ver workflow contestar-por-peticao node "Claude
# Gerador de Contestacao").
SECOES_DIFFEAVEIS = (
    "tese_central",
    "preliminares",
    "merito",
    "fundamentos",
    "pedidos",
    "observacoes",
)


def diff_secoes(
    original: dict[str, Any] | None,
    editada: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Compara as secoes de duas minutas e retorna por secao:
    - `alterada`: True se houve alguma diferenca textual (ignorando whitespace)
    - `adicionado`: trechos presentes em `editada` mas nao em `original`
    - `removido`: trechos presentes em `original` mas nao em `editada`
    - `similaridade`: ratio difflib (0.0 a 1.0) — 1.0 = identico

    Robusto a ausencia de campos: secoes vazias geram alterada=False.
    """
    original = original or {}
    editada = editada or {}

    resultado: dict[str, dict[str, Any]] = {}
    for secao in SECOES_DIFFEAVEIS:
        texto_orig = _normalizar(original.get(secao))
        texto_edit = _normalizar(editada.get(secao))

        if not texto_orig and not texto_edit:
            resultado[secao] = {
                "alterada": False,
                "similaridade": 1.0,
                "adicionado": [],
                "removido": [],
            }
            continue

        if texto_orig == texto_edit:
            resultado[secao] = {
                "alterada": False,
                "similaridade": 1.0,
                "adicionado": [],
                "removido": [],
            }
            continue

        matcher = difflib.SequenceMatcher(None, texto_orig, texto_edit)
        adicionados: list[str] = []
        removidos: list[str] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert" or tag == "replace":
                trecho = texto_edit[j1:j2].strip()
                if trecho:
                    adicionados.append(trecho)
            if tag == "delete" or tag == "replace":
                trecho = texto_orig[i1:i2].strip()
                if trecho:
                    removidos.append(trecho)

        resultado[secao] = {
            "alterada": True,
            "similaridade": round(matcher.ratio(), 4),
            "adicionado": adicionados,
            "removido": removidos,
        }

    return resultado


def resumo_diff(diff: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Resumo agregado do diff para metricas (PR5 Observabilidade).

    Retorna:
    - `secoes_alteradas`: lista de nomes de secoes com `alterada=True`
    - `total_secoes_alteradas`: contagem
    - `similaridade_media`: media dos ratios (excluindo secoes vazias)
    """
    secoes_alteradas = [s for s, d in diff.items() if d["alterada"]]
    similaridades = [d["similaridade"] for d in diff.values() if d["similaridade"] is not None]
    return {
        "secoes_alteradas": secoes_alteradas,
        "total_secoes_alteradas": len(secoes_alteradas),
        "similaridade_media": (
            round(sum(similaridades) / len(similaridades), 4) if similaridades else 1.0
        ),
    }


def _normalizar(valor: Any) -> str:
    """Normaliza um valor de secao da minuta para comparacao.

    Aceita string ou dict (caso do `impugnacao_pedidos` que e map). Strings sao
    normalizadas para whitespace simples; dicts sao serializados de forma estavel.
    """
    if valor is None:
        return ""
    if isinstance(valor, dict):
        # Serializa de forma deterministica para comparacao.
        items = sorted(valor.items())
        return "\n".join(f"{k}: {_normalizar(v)}" for k, v in items)
    if isinstance(valor, list):
        return "\n".join(_normalizar(v) for v in valor)
    texto = str(valor).strip()
    # Colapsa whitespace excessivo para nao contar reformatacoes triviais.
    return " ".join(texto.split())
