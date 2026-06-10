"""PR18.1 — Self-Correction truncava em pecas com muitas citacoes.

Descoberto no teste end-to-end do PR18 (peca 0000420, 2026-06-09):
`tokens_output` bateu EXATO em max_tokens (1500) e o JSON saiu truncado no
meio do array -> parse_error em TODA a cascata de repairs (virgula nenhuma
conserta JSON cortado) -> fallback silencioso com citacoes_incertas: 0.
O advogado fica sem os avisos de citacao incerta justamente nas pecas mais
longas — as que mais precisam de verificacao.

Fix:
1. max_tokens 1500 -> 4000 (custo extra ~US$0.01/peca no Haiku).
2. Quando stop_reason === 'max_tokens', registra api_error='resposta_truncada
   (max_tokens)' ANTES de tentar o parse — diagnostico honesto em vez de
   'parse_error' generico.

Idempotente: detecta marker PR18_1.

Uso:
    python docs/_dev/_patch_pr18_1_selfcorr_max_tokens.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR18_1"


def patch_self_correction(js: str) -> str:
    old_tokens = "        model: CLAUDE_MODEL,\n        max_tokens: 1500,"
    new_tokens = (
        "        model: CLAUDE_MODEL,\n"
        "        // PR18_1: 1500 truncava a lista de citacoes em pecas longas ->\n"
        "        // JSON cortado -> fallback silencioso. 4000 cobre folga 2x acima\n"
        "        // do maior caso observado.\n"
        "        max_tokens: 4000,"
    )
    if old_tokens not in js:
        raise RuntimeError("anchor do max_tokens do Self-Correction nao encontrado")
    js = js.replace(old_tokens, new_tokens, 1)

    # Diagnostico de truncamento antes do parse.
    old_raw = (
        "      const raw = (payload.content || []).filter(b => b.type === 'text')"
        ".map(b => b.text).join('').trim();\n"
        "      if (raw) {"
    )
    new_raw = (
        "      const raw = (payload.content || []).filter(b => b.type === 'text')"
        ".map(b => b.text).join('').trim();\n"
        "      // PR18_1: truncamento por max_tokens gera JSON cortado que nenhum\n"
        "      // repair conserta — registra a causa real em vez de parse_error.\n"
        "      if (payload.stop_reason === 'max_tokens') {\n"
        "        apiError = 'resposta_truncada (max_tokens)';\n"
        "      } else if (raw) {"
    )
    if old_raw not in js:
        raise RuntimeError("anchor do bloco raw do Self-Correction nao encontrado")
    return js.replace(old_raw, new_raw, 1)


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    node = next(
        (n for n in wf["nodes"] if n.get("id") == "node-self-correction-peticao"), None
    )
    if node is None:
        print("ERRO: node Self-Correction nao encontrado", file=sys.stderr)
        return 1

    js = node["parameters"]["jsCode"]
    if MARKER in js:
        print(f"Ja contem marker {MARKER}. Nada a fazer.")
        return 0

    node["parameters"]["jsCode"] = patch_self_correction(js)
    wf["description"] = (
        wf.get("description", "")
        + " | PR18.1: Self-Correction max_tokens 1500->4000 + diagnostico de truncamento."
    )
    wf["updatedAt"] = "2026-06-09T23:30:00.000Z"
    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: {MARKER} aplicado em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
