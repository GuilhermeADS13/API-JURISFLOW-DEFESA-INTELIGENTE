"""PR17 — fecha as lacunas do JSON-repair apontadas na revisao de 2026-06-09.

O PR16 v2 corrigiu o padrao 'vırgula faltante em arrays' (Haiku, pecas #43/#44)
apenas no Self-Correction. Esta revisao encontrou tres lacunas:

1. **Detector de Contradicoes** (roda no Haiku por default — o modelo mais
   propenso ao bug) nao tinha NENHUM repair: parse_error fazia `contradicoes`
   voltar vazio silenciosamente e o advogado nunca via o aviso.
2. **Gerador** tinha so o repair v1 inline (aspas/quebras) — sem o v2, o
   padrao `}{` sem vırgula em documentos_anexos[]/riscos[] derrubava a
   geracao inteira pro fallback.
3. **inserirVirgulasFaltantes** prometia no comentario tratar fechamento de
   string como fim de elemento, mas so tratava '}' e ']' — `["a" "b"]` nao
   era reparado. v3 cobre esse caso (':' nao dispara o gatilho, entao chave
   de objeto `{"key": ...}` fica intacta).

Bonus: custo_estimado_usd do Detector e do Self-Correction agora escolhe o
preco por Mtok conforme o modelo efetivo (CLAUDE_VERIFICACAO_MODEL pode
apontar pra haiku/sonnet/opus) em vez de hardcodar o preco de um modelo so.
Remove tambem o `TIMEOUT_MS` morto do Self-Correction.

Idempotente: detecta marker PR17_REPAIR.

Uso:
    python docs/_dev/_patch_pr17_repair_todos_nodes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "PR17_REPAIR"

# ── Funcao v1 (copia do Self-Correction) — vai pro Detector ─────────────────
REPAIR_V1_FUNC = r"""
// PR17_REPAIR: repair heuristico v1 (aspas internas nao escapadas + quebras
// de linha literais dentro de strings). Mesmo algoritmo do Self-Correction.
function repairJsonMalformado(fenced) {
  let repaired = '', inStr = false, esc = false;
  for (let i = 0; i < fenced.length; i++) {
    const ch = fenced[i];
    if (esc) { repaired += ch; esc = false; continue; }
    if (ch === '\\') { repaired += ch; esc = true; continue; }
    if (ch === '"') {
      if (!inStr) { repaired += ch; inStr = true; continue; }
      let j = i + 1; while (j < fenced.length && /\s/.test(fenced[j])) j++;
      const nx = fenced[j];
      if (nx === undefined || nx === ',' || nx === ':' || nx === '}' || nx === ']') { repaired += ch; inStr = false; }
      else { repaired += '\\"'; }
      continue;
    }
    if (inStr && (ch === '\n' || ch === '\r' || ch === '\t')) {
      repaired += ch === '\n' ? '\\n' : ch === '\r' ? '\\r' : '\\t';
      continue;
    }
    repaired += ch;
  }
  return repaired;
}
"""

# ── Funcao v3 — vai pro Detector e pro Gerador ──────────────────────────────
REPAIR_V3_FUNC = r"""
// PR17_REPAIR: virgulas faltantes entre elementos JSON (v3 — cobre tambem
// fechamento de string seguido de novo elemento: ["a" "b"], {"a":"x" "b":"y"}).
// So roda em JSON que JA falhou no parse; ':' nao dispara o gatilho, entao
// chave de objeto ({"key": ...}) fica intacta.
function inserirVirgulasFaltantes(s) {
  let out = '', inStr = false, esc = false;
  const abreNovoElemento = (i) => {
    let j = i + 1;
    while (j < s.length && /\s/.test(s[j])) j++;
    const nx = s[j];
    return nx === '{' || nx === '[' || nx === '"';
  };
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    out += ch;
    if (esc) { esc = false; continue; }
    if (ch === '\\') { esc = true; continue; }
    if (ch === '"') {
      inStr = !inStr;
      if (!inStr && abreNovoElemento(i)) out += ',';
      continue;
    }
    if (inStr) continue;
    if ((ch === '}' || ch === ']') && abreNovoElemento(i)) out += ',';
  }
  return out;
}
"""

# Preco [input, output] por Mtok conforme modelo efetivo.
PRECO_LINE = (
    "\n// PR17_REPAIR: preco por Mtok conforme modelo efetivo (haiku $1/$5,"
    "\n// opus $5/$25, default sonnet $3/$15) — antes o preco era hardcoded."
    "\nconst PRECO_MTOK = /haiku/i.test(CLAUDE_MODEL) ? [1, 5]"
    " : /opus/i.test(CLAUDE_MODEL) ? [5, 25] : [3, 15];\n"
)


def _insere_antes_envelope(js: str, bloco: str) -> str:
    anchor = "const envelope = $input.first().json;"
    if anchor not in js:
        raise RuntimeError("anchor 'const envelope' nao encontrado")
    return js.replace(anchor, bloco + "\n" + anchor, 1)


def patch_detector(js: str) -> str:
    """Detector: insere v1 + v3 e troca o parse seco pela cascata de repairs."""
    old_catch = (
        "        try {\n"
        "          resultado = JSON.parse(stripFences(raw));\n"
        "          provider = 'claude';\n"
        "        } catch (e) {\n"
        "          apiError = `parse_error: ${e.message}`;\n"
        "        }"
    )
    new_catch = (
        "        const fenced = stripFences(raw);\n"
        "        try {\n"
        "          resultado = JSON.parse(fenced);\n"
        "          provider = 'claude';\n"
        "        } catch (e) {\n"
        "          // PR17_REPAIR — cascata de repairs (v1 aspas/quebras, v3 virgulas\n"
        "          // sobre o v1 e sobre o ORIGINAL — v1 pode mutilar casos que o v3\n"
        "          // resolveria sozinho). Haiku eh o modelo mais propenso a JSON\n"
        "          // malformado; sem isso o parse_error zerava contradicoes[]\n"
        "          // silenciosamente.\n"
        "          let reparado = repairJsonMalformado(fenced);\n"
        "          try {\n"
        "            resultado = JSON.parse(reparado);\n"
        "            provider = 'claude_repaired';\n"
        "          } catch (e2) {\n"
        "            try {\n"
        "              resultado = JSON.parse(inserirVirgulasFaltantes(reparado));\n"
        "              provider = 'claude_repaired_v2';\n"
        "            } catch (e3) {\n"
        "              try {\n"
        "                resultado = JSON.parse(inserirVirgulasFaltantes(fenced));\n"
        "                provider = 'claude_repaired_v3';\n"
        "              } catch (e4) {\n"
        "                apiError = `parse_error: ${e.message}`;\n"
        "              }\n"
        "            }\n"
        "          }\n"
        "        }"
    )
    if old_catch not in js:
        raise RuntimeError("catch antigo do Detector nao encontrado")
    js = js.replace(old_catch, new_catch, 1)
    js = _insere_antes_envelope(js, REPAIR_V1_FUNC + REPAIR_V3_FUNC)

    # Custo model-aware.
    model_line = "const CLAUDE_MODEL = readEnv('CLAUDE_VERIFICACAO_MODEL') || 'claude-haiku-4-5';"
    if model_line not in js:
        raise RuntimeError("linha CLAUDE_MODEL do Detector nao encontrada")
    js = js.replace(model_line, model_line + PRECO_LINE, 1)
    old_custo = "((tokens_input/1000000*1) + (tokens_output/1000000*5))"
    new_custo = "((tokens_input/1000000*PRECO_MTOK[0]) + (tokens_output/1000000*PRECO_MTOK[1]))"
    if old_custo not in js:
        raise RuntimeError("expressao de custo do Detector nao encontrada")
    return js.replace(old_custo, new_custo, 1)


def patch_gerador(js: str) -> str:
    """Gerador: insere v3 e adiciona a 2a passada na cauda do repair inline."""
    old_tail = "try { minuta = JSON.parse(repaired); } catch { throw jsonErr; }"
    new_tail = (
        "try { minuta = JSON.parse(repaired); } catch { "
        "/* PR17_REPAIR: passadas extras — virgulas faltantes sobre o repaired e "
        "sobre o fenced ORIGINAL (o repair de aspas pode mutilar casos que so "
        "precisavam de virgula) */ "
        "try { minuta = JSON.parse(inserirVirgulasFaltantes(repaired)); } "
        "catch { try { minuta = JSON.parse(inserirVirgulasFaltantes(fenced)); } "
        "catch { throw jsonErr; } } }"
    )
    if old_tail not in js:
        raise RuntimeError("cauda do repair inline do Gerador nao encontrada")
    js = js.replace(old_tail, new_tail, 1)
    return _insere_antes_envelope(js, REPAIR_V3_FUNC)


def patch_self_correction(js: str) -> str:
    """Self-Correction: upgrade do v2 pra v3 + custo model-aware + remove TIMEOUT morto."""
    # v2 -> v3: a linha do toggle de string passa a checar fim de elemento.
    old_quote = "if (ch === '\"') { inStr = !inStr; continue; }"
    new_quote = (
        "if (ch === '\"') {\n"
        "      inStr = !inStr;\n"
        "      // PR17_REPAIR (v3): fechamento de string seguido de novo elemento\n"
        "      // tambem indica virgula faltante (ex: [\"a\" \"b\"]).\n"
        "      let j = i + 1;\n"
        "      while (j < s.length && /\\s/.test(s[j])) j++;\n"
        "      const nx = s[j];\n"
        "      if (!inStr && (nx === '{' || nx === '[' || nx === '\"')) out += ',';\n"
        "      continue;\n"
        "    }"
    )
    if old_quote not in js:
        raise RuntimeError("linha do toggle de string do v2 nao encontrada no Self-Correction")
    js = js.replace(old_quote, new_quote, 1)

    # Cascata ganha 4a tentativa: v3 sobre o fenced ORIGINAL (o repair v1 de
    # aspas pode mutilar entradas que so precisavam de virgula).
    old_e3 = (
        "            } catch (e3) {\n"
        "              apiError = `parse_error: ${jsonErr.message}`;\n"
        "            }"
    )
    new_e3 = (
        "            } catch (e3) {\n"
        "              try {\n"
        "                resultado = JSON.parse(inserirVirgulasFaltantes(fenced));\n"
        "                provider = 'claude_repaired_v3';\n"
        "              } catch (e4) {\n"
        "                apiError = `parse_error: ${jsonErr.message}`;\n"
        "              }\n"
        "            }"
    )
    if old_e3 not in js:
        raise RuntimeError("catch e3 do Self-Correction nao encontrado")
    js = js.replace(old_e3, new_e3, 1)

    model_line = (
        "const CLAUDE_MODEL = readEnv('CLAUDE_VERIFICACAO_MODEL') || "
        "readEnv('CLAUDE_MODEL') || 'claude-sonnet-4-6';"
    )
    if model_line not in js:
        raise RuntimeError("linha CLAUDE_MODEL do Self-Correction nao encontrada")
    js = js.replace(model_line, model_line + PRECO_LINE, 1)

    old_custo = "((tokens_input/1000000*3) + (tokens_output/1000000*15))"
    new_custo = "((tokens_input/1000000*PRECO_MTOK[0]) + (tokens_output/1000000*PRECO_MTOK[1]))"
    if old_custo not in js:
        raise RuntimeError("expressao de custo do Self-Correction nao encontrada")
    js = js.replace(old_custo, new_custo, 1)

    # Dead code: __FETCH usa timeout fixo de 480000; essa const nunca foi lida.
    return js.replace("const TIMEOUT_MS = 60000;\n", "", 1)


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    nodes = {n["id"]: n for n in wf["nodes"]}
    alvos = {
        "node-detector-contradicoes": patch_detector,
        "node-gerador-peticao": patch_gerador,
        "node-self-correction-peticao": patch_self_correction,
    }

    # Resolve por id; se o id do detector divergir, cai pro match por nome.
    if "node-detector-contradicoes" not in nodes:
        det = next((n for n in wf["nodes"] if "Detector" in n["name"]), None)
        if det is None:
            print("ERRO: node Detector nao encontrado", file=sys.stderr)
            return 1
        alvos[det["id"]] = alvos.pop("node-detector-contradicoes")

    mudou_algum = False
    for node_id, patch_fn in alvos.items():
        node = nodes.get(node_id)
        if node is None:
            print(f"ERRO: node {node_id} nao encontrado", file=sys.stderr)
            return 1
        js = node["parameters"]["jsCode"]
        if MARKER in js:
            print(f"{node['name']}: ja contem {MARKER}, pulando.")
            continue
        node["parameters"]["jsCode"] = patch_fn(js)
        mudou_algum = True
        print(f"{node['name']}: patch aplicado.")

    if not mudou_algum:
        print("Nada a fazer.")
        return 0

    wf["description"] = (
        wf.get("description", "")
        + " | PR17: repair em cascata no Detector + v2 no Gerador + v3 cobre strings; custo por modelo."
    )
    wf["updatedAt"] = "2026-06-09T21:00:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: {MARKER} aplicado em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
