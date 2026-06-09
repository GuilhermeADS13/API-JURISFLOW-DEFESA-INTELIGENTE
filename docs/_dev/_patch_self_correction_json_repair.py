"""Patcha o node Self-Correction Citacoes (PR16 Bug #2): adiciona JSON-repair
heuristico no parse da resposta da Haiku, igual ao que o Gerador ja faz.

Sintoma observado: peca #43 caiu em fallback do Self-Correction com erro
'parse_error: Expected \\',\\' or \\']\\' after array element in JSON at position
3969 (line 170 column 6)' — Haiku produziu JSON malformado e nao tem
heuristica de repair (so o Gerador tem).

Idempotente: detecta marker PR16_JSON_REPAIR no JS.

Uso:
    python docs/_dev/_patch_self_correction_json_repair.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR16_JSON_REPAIR"

# Bloco JS de repair — mesma logica do Gerador, simplificada pro Self-Correction.
REPAIR_FUNC = f"""// {MARKER}: repair heuristico de JSON malformado (Haiku as vezes esquece
// vírgula ou quebra linha dentro de string). Mesmo algoritmo do Gerador.
function repairJsonMalformado(fenced) {{
  let repaired = '', inStr = false, esc = false;
  for (let i = 0; i < fenced.length; i++) {{
    const ch = fenced[i];
    if (esc) {{ repaired += ch; esc = false; continue; }}
    if (ch === '\\\\') {{ repaired += ch; esc = true; continue; }}
    if (ch === '"') {{
      if (!inStr) {{ repaired += ch; inStr = true; continue; }}
      let j = i + 1; while (j < fenced.length && /\\s/.test(fenced[j])) j++;
      const nx = fenced[j];
      if (nx === undefined || nx === ',' || nx === ':' || nx === '}}' || nx === ']') {{ repaired += ch; inStr = false; }}
      else {{ repaired += '\\\\"'; }}
      continue;
    }}
    if (inStr && (ch === '\\n' || ch === '\\r' || ch === '\\t')) {{
      repaired += ch === '\\n' ? '\\\\n' : ch === '\\r' ? '\\\\r' : '\\\\t';
      continue;
    }}
    repaired += ch;
  }}
  return repaired;
}}
"""


def patch_self_correction(js: str) -> tuple[str, bool]:
    """Injeta repair antes do try/catch do JSON.parse no Self-Correction."""
    if MARKER in js:
        return js, False

    # Bloco antigo de parse (sem repair):
    old_parse_block = (
        "        try {\n"
        "          resultado = JSON.parse(stripFences(raw));\n"
        "          provider = 'claude';\n"
        "        } catch (e) {\n"
        "          apiError = `parse_error: ${e.message}`;\n"
        "        }"
    )
    # Bloco novo com repair fallback:
    new_parse_block = (
        "        const fenced = stripFences(raw);\n"
        "        try {\n"
        "          resultado = JSON.parse(fenced);\n"
        "          provider = 'claude';\n"
        "        } catch (jsonErr) {\n"
        "          // PR16 Bug #2 — tenta repair heuristico antes de cair em fallback\n"
        "          try {\n"
        "            resultado = JSON.parse(repairJsonMalformado(fenced));\n"
        "            provider = 'claude_repaired';\n"
        "          } catch (e2) {\n"
        "            apiError = `parse_error: ${jsonErr.message}`;\n"
        "          }\n"
        "        }"
    )

    if old_parse_block not in js:
        raise RuntimeError(
            "Bloco antigo de parse do Self-Correction nao encontrado — "
            "verifique se o template mudou."
        )

    # Insere a funcao repairJsonMalformado uma vez, antes do envelope = $input.first().json
    anchor_funcao = "const envelope = $input.first().json;"
    if anchor_funcao not in js:
        raise RuntimeError("Anchor 'const envelope = $input.first().json;' nao encontrado")
    js = js.replace(anchor_funcao, REPAIR_FUNC + "\n" + anchor_funcao, 1)

    # Substitui o bloco de parse
    js = js.replace(old_parse_block, new_parse_block, 1)
    return js, True


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    node = next(
        (n for n in wf["nodes"] if n.get("id") == "node-self-correction-peticao"), None
    )
    if node is None:
        print("ERRO: node Self-Correction Citacoes nao encontrado", file=sys.stderr)
        return 1

    js_novo, mudou = patch_self_correction(node["parameters"]["jsCode"])
    if not mudou:
        print(f"Workflow ja contem marker {MARKER}. Nada a fazer.")
        return 0

    node["parameters"]["jsCode"] = js_novo
    wf["description"] = (
        wf.get("description", "")
        + " | PR16 Bug #2: JSON-repair no Self-Correction Citacoes."
    )
    wf["updatedAt"] = "2026-06-09T17:35:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: marker {MARKER} injetado no Self-Correction em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
