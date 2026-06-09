"""Estende o JSON-repair do Self-Correction (PR16 v2): adiciona heuristica
para inserir virgulas faltantes entre elementos de array.

Padrao do erro observado nas pecas #43 e #44:
  'Expected , or ] after array element in JSON at position ~3900'

Causa raiz: Haiku gera arrays com objetos consecutivos sem virgula:
  [{"texto": "x"}{"texto": "y"}]            // falta ',' entre } e {
  [{"texto": "x"}\\n{"texto": "y"}]          // mesmo c/ whitespace

Meu repair v1 (PR16 patch original) so atacava aspas duplas dentro de
strings — nao corrigia esse caso. v2 adiciona segunda passada que insere
',' onde necessario.

Idempotente: detecta marker PR16_JSON_REPAIR_V2.

Uso:
    python docs/_dev/_patch_self_correction_repair_v2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR16_JSON_REPAIR_V2"

# Funcao NOVA: pass extra pra inserir virgulas faltantes em arrays.
# Implementacao: walking parser que detecta '}' ou ']' ou '"' (fim de elemento)
# seguido de whitespace + '{' ou '[' ou '"' (inicio de novo elemento) — insere
# virgula no meio. Conservador: NUNCA modifica nada dentro de string.
INSERIR_VIRGULAS_FUNC = f"""
// {MARKER}: 2a passada do repair — insere virgulas faltantes entre elementos
// de array/objeto. Cobre padrao Haiku '[{{"x":1}}{{"x":2}}]' (sem virgula).
function inserirVirgulasFaltantes(s) {{
  let out = '', inStr = false, esc = false;
  for (let i = 0; i < s.length; i++) {{
    const ch = s[i];
    out += ch;
    if (esc) {{ esc = false; continue; }}
    if (ch === '\\\\') {{ esc = true; continue; }}
    if (ch === '"') {{ inStr = !inStr; continue; }}
    if (inStr) continue;
    // Fim de elemento: '}}' ']' ou '"' (fechamento de string)
    if (ch === '}}' || ch === ']') {{
      // Olha proximo nao-whitespace
      let j = i + 1;
      while (j < s.length && /\\s/.test(s[j])) j++;
      const nx = s[j];
      if (nx === '{{' || nx === '[' || nx === '"') {{
        // Inserir virgula apos esse fechamento
        out += ',';
      }}
    }}
  }}
  return out;
}}
"""


def patch_self_correction(js: str) -> tuple[str, bool]:
    """Adiciona segunda passada de repair (inserirVirgulasFaltantes)."""
    if MARKER in js:
        return js, False

    # Insere a nova funcao logo apos repairJsonMalformado.
    anchor = "function repairJsonMalformado(fenced)"
    if anchor not in js:
        raise RuntimeError(
            "PR16_JSON_REPAIR ainda nao aplicado — rode primeiro "
            "_patch_self_correction_json_repair.py"
        )
    # Encontra o fechamento da funcao repairJsonMalformado (procura `return repaired;\n}`)
    idx_close = js.find("return repaired;\n}", js.find(anchor))
    if idx_close == -1:
        raise RuntimeError("Fechamento de repairJsonMalformado nao encontrado")
    idx_after = idx_close + len("return repaired;\n}")
    js = js[:idx_after] + INSERIR_VIRGULAS_FUNC + js[idx_after:]

    # Atualiza o catch do parse pra rodar AS DUAS passadas em cascata:
    # tenta original -> repair v1 -> repair v1 + v2 -> fallback
    old_catch = (
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
    new_catch = (
        "        const fenced = stripFences(raw);\n"
        "        try {\n"
        "          resultado = JSON.parse(fenced);\n"
        "          provider = 'claude';\n"
        "        } catch (jsonErr) {\n"
        "          // PR16 v2 — cascata de repairs: original -> v1 (aspas/quebras)\n"
        "          // -> v1+v2 (vırgulas faltantes em arrays). So cai em fallback se\n"
        "          // todas as tentativas falharem.\n"
        "          let reparado = repairJsonMalformado(fenced);\n"
        "          try {\n"
        "            resultado = JSON.parse(reparado);\n"
        "            provider = 'claude_repaired';\n"
        "          } catch (e2) {\n"
        "            try {\n"
        "              resultado = JSON.parse(inserirVirgulasFaltantes(reparado));\n"
        "              provider = 'claude_repaired_v2';\n"
        "            } catch (e3) {\n"
        "              apiError = `parse_error: ${jsonErr.message}`;\n"
        "            }\n"
        "          }\n"
        "        }"
    )
    if old_catch not in js:
        raise RuntimeError(
            "Catch antigo do PR16 v1 nao encontrado — verifique se o template "
            "mudou ou se o patch v1 foi aplicado primeiro"
        )
    js = js.replace(old_catch, new_catch, 1)
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
        + " | PR16 v2: repair JSON insere virgulas faltantes em arrays."
    )
    wf["updatedAt"] = "2026-06-09T17:50:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: marker {MARKER} injetado no Self-Correction em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
