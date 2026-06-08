"""Patcha o Gerador (PR15): adiciona dica de tipos canonicos pro Claude usar
strings de `tipo` que casem com o normalizador do builder.

Idempotente: detecta marker `PR15_TIPO_CANONICO` no SYSTEM e nao reaplica.

Uso:
    python docs/_dev/_patch_tipo_canonico_anexos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR15_TIPO_CANONICO"

# Bloco a injetar logo APOS o bullet 'DOCUMENTOS PROBATORIOS A ANEXAR' (que ja
# tem o mapeamento pedido -> tipo de documento). Reforca a NOMENCLATURA exata
# pra max chance de match com o normalizador no backend.
NOVO_BLOCO = (
    f"\n  - [{MARKER}] NOMENCLATURA EXATA do campo 'tipo' (alinhada com o "
    "normalizador do builder no backend): use uma das strings abaixo, "
    "PRESERVANDO essas palavras-chave no inicio:\n"
    "    * 'Folha de Ponto' / 'Cartoes de Ponto' (jornada)\n"
    "    * 'Extrato FGTS' / 'Extrato Analitico FGTS'\n"
    "    * 'TRCT' / 'Termo de Rescisao'\n"
    "    * 'Laudo Pericial' / 'PPP' (insalubridade/periculosidade)\n"
    "    * 'Contrato de Trabalho'\n"
    "    * 'CTPS Digital' / 'Carteira de Trabalho'\n"
    "    * 'Prints' / 'E-mails' / 'Audios' (provas digitais)\n"
    "    * 'Outros' (fallback) — para documentos que nao se encaixem nas categorias acima\n"
    "    Quando o advogado anexar imagens dessas categorias, o sistema embeda "
    "automaticamente NO LUGAR do placeholder [ANEXAR ARQUIVO]. Strings que "
    "fujam dessas palavras-chave caem em 'outro' e nao recebem embedding."
)


def patch_gerador(js: str) -> tuple[str, bool]:
    """Adiciona bloco de nomenclatura canonica logo apos as regras existentes."""
    if MARKER in js:
        return js, False

    # Marker estavel apos o qual injetamos: ultima linha das regras de
    # documentos probatorios — 'descricao' deve ser objetiva.
    marker_anchor = "  - 'descricao' deve ser objetiva (1-2 frases) explicando O QUE prova."
    if marker_anchor not in js:
        raise RuntimeError(
            "Marker de ancoragem nao encontrado no SYSTEM — workflow mudou?"
        )
    js = js.replace(marker_anchor, marker_anchor + NOVO_BLOCO)
    return js, True


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    gerador = next(
        (n for n in wf["nodes"] if n.get("id") == "node-gerador-peticao"), None
    )
    if gerador is None:
        print("ERRO: node Gerador nao encontrado", file=sys.stderr)
        return 1

    js_novo, mudou = patch_gerador(gerador["parameters"]["jsCode"])
    if not mudou:
        print(f"Workflow ja contem marker {MARKER}. Nada a fazer.")
        return 0

    gerador["parameters"]["jsCode"] = js_novo
    wf["description"] = (
        wf.get("description", "")
        + " | PR15: nomenclatura canonica de tipo em documentos_anexos[]."
    )
    wf["updatedAt"] = "2026-06-08T21:00:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: marker {MARKER} injetado em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
