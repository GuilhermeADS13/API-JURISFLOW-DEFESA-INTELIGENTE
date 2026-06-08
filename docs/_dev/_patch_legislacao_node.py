"""Patcha o workflow (PR13 #B3): adiciona node 'Buscar Legislacao Aplicavel'
entre 'Buscar Defesas Anteriores' e 'Claude Gerador', e injeta o bloco
LEGISLACAO_VERIFICADA no USER_MSG do Gerador.

Idempotente: detecta se o node ja existe.

Uso:
    python docs/_dev/_patch_legislacao_node.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LEGISLACAO_JS = r"""// n8n 2.17.5 JS sandbox shims (process, AbortController, fetch). Tudo em const.
const __AC_INIT = (() => { if (typeof globalThis.AbortController === 'undefined') { globalThis.AbortController = class { constructor() { this.signal = undefined; } abort() {} }; } return true; })();
const __PROC = (() => { try { return process.env || {}; } catch (_) { return {}; } })();
const __HTTP = (() => { try { if ($helpers && $helpers.httpRequest) return $helpers; } catch (_) {} try { if (typeof helpers !== 'undefined' && helpers && helpers.httpRequest) return helpers; } catch (_) {} try { if (this && this.helpers && this.helpers.httpRequest) return this.helpers; } catch (_) {} return null; })();
const __FETCH = async (url, opts) => {
  opts = opts || {};
  const method = opts.method || 'GET';
  const headers = opts.headers || {};
  let body = opts.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (_) { } }
  if (!__HTTP) {
    try { const r = await fetch(url, opts); return r; } catch (_) {}
    throw new Error('http_unavailable');
  }
  try {
    const r = await __HTTP.httpRequest({ url, method, headers, body, json: true, returnFullResponse: true, ignoreHttpStatusErrors: true, timeout: 30000 });
    const status = r.statusCode || r.status || 200;
    const data = (r.body !== undefined) ? r.body : r;
    return { ok: status >= 200 && status < 300, status, json: async () => data, text: async () => (typeof data === 'string' ? data : JSON.stringify(data || {})) };
  } catch (e) {
    const status = e.statusCode || e.status || 500;
    const msg = (e.message || '').slice(0, 500);
    return { ok: false, status, json: async () => ({ error: msg }), text: async () => msg };
  }
};

// PR13 #B3 — Buscar Legislacao Aplicavel
// Antes do Gerador montar a peca, busca leis/sumulas relevantes via RAG
// hibrido em public.legislacao. O Gerador recebe verbatim e injeta no
// SYSTEM, eliminando alucinacao de citacoes na origem.
//
// Falha silenciosa: erro/timeout -> envelope.legislacao_aplicavel = [] e
// o Gerador segue normalmente (com o risco original de alucinar). Esse
// node eh otimizacao, nao requisito.

const envelope = $input.first().json;
if (envelope.status === 'erro_validacao') return [{ json: envelope }];

const readEnv = (key, fb = '') => {
  try {
    if (typeof $vars !== 'undefined' && $vars && $vars[key]) return String($vars[key]).trim();
    return ($env && $env[key]) ? String($env[key]).trim() : (__PROC[key] || fb);
  } catch { return __PROC[key] || fb; }
};

const dados = envelope.dados_extraidos || {};
const defesas = (envelope.defesas_anteriores || {}).casos || [];
const teseHint = defesas.length > 0 ? (defesas[0].tese_central || '') : '';

const BACKEND_URL = readEnv('BACKEND_URL', 'http://autojuri_backend:8000');
const ADMIN_TOKEN = readEnv('BACKEND_ADMIN_TOKEN', '');

let legislacao_aplicavel = [];

if (ADMIN_TOKEN) {
  try {
    const resp = await __FETCH(BACKEND_URL + '/api/legislacao/buscar', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + ADMIN_TOKEN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fatos: dados.fatos_resumo || '',
        pedidos: Array.isArray(dados.pedidos) ? dados.pedidos : [],
        tese_central: teseHint,
        area_juridica: dados.area_juridica || null,
      }),
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data && Array.isArray(data.leis)) {
        legislacao_aplicavel = data.leis;
      }
    }
  } catch (_) { /* silencioso — legislacao eh opcional */ }
}

return [{ json: { ...envelope, legislacao_aplicavel } }];
"""


def _build_legislacao_block_replacement() -> tuple[str, str]:
    """Retorna (old, new) pra patchar o USER_MSG do Gerador injetando bloco verbatim."""
    # No JS do Gerador, USER_MSG eh construido com defesasCtx ao final. Adiciono
    # tambem legislacaoCtx logo apos.
    old = "${defesasCtx}`;"
    new = """${defesasCtx}\n${(() => {
  const leis = envelope.legislacao_aplicavel || [];
  if (!Array.isArray(leis) || leis.length === 0) return '';
  const linhas = leis.map(l => `- ${l.origem} ${l.numero}: ${(l.texto || '').replace(/\\s+/g, ' ').slice(0, 400)}`).join('\\n');
  return `\\n\\n================================================================\\n== LEGISLACAO VERIFICADA (cite TEXTUALMENTE no campo \\`fundamentos\\`, NAO parafraseie) ==\\n================================================================\\n${linhas}\\n================================================================`;
})()}`;"""
    return old, new


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    if any(n.get("id") == "node-buscar-legislacao" for n in wf["nodes"]):
        print("Workflow ja contem 'Buscar Legislacao Aplicavel'. Nada a fazer.")
        return 0

    # 1. Adiciona node novo
    novo_node = {
        "id": "node-buscar-legislacao",
        "name": "Buscar Legislacao Aplicavel",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1080, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": LEGISLACAO_JS,
        },
    }

    # Desloca os nodes ate o Responder pra abrir espaco visual
    desloc = {
        "node-gerador-peticao": 1280,
        "node-self-correction-peticao": 1460,
        "node-detector-contradicoes": 1640,
        "node-responder-peticao": 1840,
    }
    for node in wf["nodes"]:
        if node.get("id") in desloc:
            node["position"] = [desloc[node["id"]], 300]

    # Insere logo apos 'Buscar Defesas Anteriores Supabase' no array
    idx_after_buscar = next(
        (i for i, n in enumerate(wf["nodes"]) if n.get("id") == "node-buscar-defesas-peticao"),
        None,
    )
    if idx_after_buscar is None:
        print("ERRO: node 'Buscar Defesas Anteriores Supabase' nao encontrado", file=sys.stderr)
        return 1
    wf["nodes"].insert(idx_after_buscar + 1, novo_node)

    # 2. Rewire: Buscar Defesas -> Buscar Legislacao -> Claude Gerador
    wf["connections"]["Buscar Defesas Anteriores Supabase"] = {
        "main": [[{"node": "Buscar Legislacao Aplicavel", "type": "main", "index": 0}]]
    }
    wf["connections"]["Buscar Legislacao Aplicavel"] = {
        "main": [[{"node": "Claude Gerador de Contestacao", "type": "main", "index": 0}]]
    }

    # 3. Patcha USER_MSG do Gerador pra injetar bloco verbatim de legislacao
    gerador = next(
        (n for n in wf["nodes"] if n.get("id") == "node-gerador-peticao"), None
    )
    if gerador is None:
        print("ERRO: node 'Claude Gerador' nao encontrado", file=sys.stderr)
        return 1
    js_ger = gerador["parameters"]["jsCode"]
    old, new = _build_legislacao_block_replacement()
    if old not in js_ger:
        print(f"AVISO: nao encontrei marker '{old[:60]}' no Gerador — injecao de legislacao no USER_MSG NAO feita")
        print("       (node novo continua adicionado; SYSTEM nao recebe leis verbatim ate ajuste manual)")
    else:
        gerador["parameters"]["jsCode"] = js_ger.replace(old, new)
        print("OK: USER_MSG do Gerador patchado pra injetar legislacao verbatim")

    wf["description"] = (
        wf.get("description", "")
        + " | PR13 #B3: Buscar Legislacao Aplicavel + injecao verbatim no USER_MSG do Gerador."
    )
    wf["updatedAt"] = "2026-06-08T19:00:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: 'Buscar Legislacao Aplicavel' inserido em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
