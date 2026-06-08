"""Patcha o workflow contestar-por-peticao.json adicionando o node
Detector de Contradicoes entre Self-Correction Citacoes e Responder.

Uso:
    python docs/_dev/_patch_detector_contradicoes.py

Reescreve `docs/n8n_workflow_contestar_por_peticao.json` in-place. Idempotente:
detecta se o node ja existe e nao duplica.

Apos rodar, re-import via:
    curl -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \\
        -H "Content-Type: application/json" \\
        --data @docs/n8n_workflow_contestar_por_peticao.json \\
        http://localhost:5678/api/v1/workflows
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DETECTOR_JS = r"""// n8n 2.17.5 JS sandbox shims (process, AbortController, fetch). Tudo em const.
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
    const r = await __HTTP.httpRequest({ url, method, headers, body, json: true, returnFullResponse: true, ignoreHttpStatusErrors: true, timeout: 480000 });
    const status = r.statusCode || r.status || 200;
    const data = (r.body !== undefined) ? r.body : r;
    return { ok: status >= 200 && status < 300, status, json: async () => data, text: async () => (typeof data === 'string' ? data : JSON.stringify(data || {})) };
  } catch (e) {
    const status = e.statusCode || e.status || 500;
    const msg = (e.message || '').slice(0, 500);
    return { ok: false, status, json: async () => ({ error: msg }), text: async () => msg };
  }
};

// PR12 #10 — Detector de Contradicoes (Guia v4 §10)
// Apos o Self-Correction validar citacoes, esta etapa pede ao Claude Haiku
// para auditar se a minuta CONTRADIZ fatos extraidos da peticao inicial.
// Detecta: partes invertidas, datas erradas, valores divergentes, teses
// incompativeis. Pega o pior caso possivel — peça contradizendo dados do
// autor — antes de chegar ao advogado.
//
// Custo: ~1 chamada Claude Haiku 4.5 (~1500 tokens out, T=0.0). Vale a pena.

async function callClaudeWithRetry(url, opts, maxRetries) {
  const RETRIES = maxRetries || 3;
  const BACKOFF = [1000, 2000, 4000];
  let lastErr = null;
  for (let i = 0; i < RETRIES; i++) {
    try {
      const r = await __FETCH(url, opts);
      if (r.status === 429 || r.status === 529 || r.status === 500) {
        if (i < RETRIES - 1) {
          await new Promise(res => setTimeout(res, BACKOFF[i] || 4000));
          lastErr = { status: r.status, msg: `retryable_${r.status}` };
          continue;
        }
      }
      return r;
    } catch (e) {
      lastErr = { status: 500, msg: e.message || String(e) };
      if (i < RETRIES - 1) {
        await new Promise(res => setTimeout(res, BACKOFF[i] || 4000));
        continue;
      }
    }
  }
  return { ok: false, status: (lastErr && lastErr.status) || 500, json: async () => ({ error: (lastErr && lastErr.msg) || 'all_retries_failed' }), text: async () => (lastErr && lastErr.msg) || 'all_retries_failed' };
}

const envelope = $input.first().json;
if (envelope.status !== 'ok' || !envelope.minuta) {
  return [{ json: envelope }];
}

const readEnv = (key, fb = '') => {
  try {
    if (typeof $vars !== 'undefined' && $vars && $vars[key]) return String($vars[key]).trim();
    if (typeof $env !== 'undefined' && $env && $env[key]) return String($env[key]).trim();
  } catch (_) {}
  return __PROC[key] || fb;
};

const stripFences = s => {
  const cleaned = String(s || '').trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
  const first = cleaned.indexOf('{');
  const last = cleaned.lastIndexOf('}');
  if (first === -1 || last === -1 || last < first) return cleaned;
  return cleaned.slice(first, last + 1);
};

const ANTHROPIC_KEY = readEnv('ANTHROPIC_API_KEY') || readEnv('CLAUDE_API_KEY');
const CLAUDE_MODEL = readEnv('CLAUDE_VERIFICACAO_MODEL') || 'claude-haiku-4-5';
const BASE_URL = (readEnv('ANTHROPIC_BASE_URL') || 'https://api.anthropic.com').replace(/\/$/, '');
const API_VERSION = readEnv('ANTHROPIC_VERSION') || '2023-06-01';

const dados = envelope.dados_extraidos || {};
const m = envelope.minuta;

const dadosPeticao = JSON.stringify({
  autor: dados.autor || null,
  reu: dados.reu || null,
  numero_processo: dados.numero_processo || null,
  tipo_acao: dados.tipo_acao || null,
  vara: dados.vara || null,
  fatos_resumo: (dados.fatos_resumo || '').slice(0, 2000),
  pedidos: dados.pedidos || [],
  valores: dados.valores || {},
  argumentos_autor: (dados.argumentos_autor || []).slice(0, 5),
}, null, 2);

const textoMinuta = [
  m.tese_central, m.cabecalho_processual, m.preliminares, m.merito, m.fundamentos, m.pedidos,
].filter(Boolean).join('\n\n').slice(0, 6000);

const SYSTEM_DETECTOR = `Voce eh um auditor juridico criterioso. Sua unica funcao eh comparar os DADOS EXTRAIDOS da peticao inicial com o TEXTO DA MINUTA de contestacao gerada, e identificar CONTRADICOES factuais — afirmacoes na minuta que entrem em conflito com os fatos narrados pelo autor.

Retorne SOMENTE JSON valido (sem markdown, sem codeblock):
{
  "contradicoes": [
    {"tipo": "partes|data|valor|tese|outros", "trecho_peticao": "snippet curto do dado extraido", "trecho_minuta": "snippet curto da minuta contradizente", "descricao": "explicacao em 1 frase", "severidade": "alta|media|baixa"}
  ]
}

REGRAS:
- "alta": contradicao factual evidente (parte invertida, data > N anos divergente, valor > 50% divergente, nome do autor/reu errado, numero do processo errado).
- "media": divergencia parcial (data fora do range mas dentro do mesmo ano, valor 10-50% divergente, citacao de fato similar mas com detalhe trocado).
- "baixa": divergencia interpretativa (a tese da minuta argumenta contra o autor — isso eh ESPERADO em contestacao e NAO eh contradicao; so marque baixa se houver erro factual menor).
- NAO marque como contradicao argumentacao adversarial — a contestacao DEVE atacar a tese do autor. So conte como contradicao se a minuta AFIRMAR fato que entra em conflito com fato EXTRAIDO da peticao.
- Se nao houver contradicoes, retorne {"contradicoes": []}.
- "trecho_*" max 200 chars.`;

const USER_DETECTOR = `DADOS EXTRAIDOS DA PETICAO:
${dadosPeticao}

TEXTO DA MINUTA GERADA:
${textoMinuta}`;

let resultado = { contradicoes: [] };
let provider = 'fallback';
let apiError = null;
let tokens_input = 0, tokens_output = 0;

if (ANTHROPIC_KEY) {
  try {
    const resp = await callClaudeWithRetry(`${BASE_URL}/v1/messages`, {
      method: 'POST',
      headers: {
        'x-api-key': ANTHROPIC_KEY,
        'anthropic-version': API_VERSION,
        'content-type': 'application/json',
        'anthropic-beta': 'prompt-caching-2024-07-31',
      },
      body: {
        model: CLAUDE_MODEL,
        max_tokens: 1500,
        temperature: 0,
        system: [{ type: 'text', text: SYSTEM_DETECTOR, cache_control: { type: 'ephemeral' } }],
        messages: [{ role: 'user', content: USER_DETECTOR }],
      },
    });

    if (resp.ok) {
      const payload = await resp.json();
      if (payload && payload.usage) {
        tokens_input = parseInt(payload.usage.input_tokens, 10) || 0;
        tokens_output = parseInt(payload.usage.output_tokens, 10) || 0;
      }
      const raw = (payload.content || []).filter(b => b.type === 'text').map(b => b.text).join('').trim();
      if (raw) {
        try {
          resultado = JSON.parse(stripFences(raw));
          provider = 'claude';
        } catch (e) {
          apiError = `parse_error: ${e.message}`;
        }
      } else {
        apiError = 'resposta_vazia';
      }
    } else {
      apiError = `http_${resp.status}`;
    }
  } catch (e) {
    apiError = e.message || 'erro_desconhecido';
  }
} else {
  apiError = 'sem_chave_anthropic';
}

const contradicoes = Array.isArray(resultado.contradicoes) ? resultado.contradicoes : [];
const sanitizadas = [];
for (const c of contradicoes) {
  if (!c || typeof c !== 'object') continue;
  sanitizadas.push({
    tipo: ['partes', 'data', 'valor', 'tese', 'outros'].includes(String(c.tipo)) ? String(c.tipo) : 'outros',
    trecho_peticao: String(c.trecho_peticao || '').slice(0, 200),
    trecho_minuta: String(c.trecho_minuta || '').slice(0, 200),
    descricao: String(c.descricao || '').slice(0, 300),
    severidade: ['alta', 'media', 'baixa'].includes(String(c.severidade)) ? String(c.severidade) : 'baixa',
  });
}

return [{
  json: {
    ...envelope,
    contradicoes: sanitizadas,
    detector_contradicoes: {
      provider, model: CLAUDE_MODEL, api_error: apiError,
      tokens_input, tokens_output, tokens_total: tokens_input + tokens_output,
      custo_estimado_usd: tokens_input || tokens_output ? parseFloat(((tokens_input/1000000*1) + (tokens_output/1000000*5)).toFixed(6)) : 0,
    },
  },
}];
"""


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    wf_path = base / "docs" / "n8n_workflow_contestar_por_peticao.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))

    # Idempotencia: ja patchado?
    if any(n.get("id") == "node-detector-contradicoes" for n in wf["nodes"]):
        print("Workflow ja contem 'Detector de Contradicoes'. Nada a fazer.")
        return 0

    detector_node = {
        "id": "node-detector-contradicoes",
        "name": "Detector de Contradicoes",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1440, 300],
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": DETECTOR_JS,
        },
    }

    # Move Responder p/ direita pra abrir espaco visual
    for node in wf["nodes"]:
        if node.get("id") == "node-responder-peticao":
            node["position"] = [1660, 300]

    # Insere o detector logo antes do Responder no array
    idx_responder = next(
        (i for i, n in enumerate(wf["nodes"]) if n.get("id") == "node-responder-peticao"),
        None,
    )
    if idx_responder is None:
        print("ERRO: node 'Responder' nao encontrado", file=sys.stderr)
        return 1
    wf["nodes"].insert(idx_responder, detector_node)

    # Rewire: Self-Correction -> Detector -> Responder (antes era SC -> Responder)
    wf["connections"]["Self-Correction Citacoes"] = {
        "main": [[{"node": "Detector de Contradicoes", "type": "main", "index": 0}]]
    }
    wf["connections"]["Detector de Contradicoes"] = {
        "main": [[{"node": "Responder", "type": "main", "index": 0}]]
    }

    # Atualiza metadado
    wf["description"] = (
        wf.get("description", "")
        + " | PR12 #10: Detector de Contradicoes (Haiku 4.5) entre Self-Correction e Responder."
    )
    wf["updatedAt"] = "2026-06-05T00:00:00.000Z"

    wf_path.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"OK: Detector de Contradicoes inserido em {wf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
