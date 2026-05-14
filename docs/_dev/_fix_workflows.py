"""Limpa Code nodes dos 3 workflows n8n e re-aplica patch consistente.

n8n 2.17.5 + JS Task Runner externo: sandbox NAO expoe `process` nem
`AbortController` no escopo direto, mas expoe `globalThis`, `fetch`,
`setTimeout`, `Promise`, etc.

Este script:
1. Remove qualquer prepend antigo (linhas de helpers que adicionei em
   tentativas anteriores) — detecta pelos comentarios marcadores.
2. Reverte qualquer __PROC residual para process.env (cleanup).
3. Reverte __fetchTO residual para fetch (cleanup).
4. Re-aplica patch limpo: mock de AbortController via globalThis e
   `__PROC` via try/catch. Fetch continua chamando AbortController mockado
   (no-op) — a chamada nunca dispara o sandbox porque AbortController vira
   classe valida antes de qualquer codigo do node executar.
"""

import json
import re
from pathlib import Path

DOCS = Path(r"c:\Users\lakil\Downloads\PROJETO API-CONTESTACAO\API-CONTESTACAO\docs")

ARQUIVOS = [
    "n8n_workflow_contestar_por_peticao.json",
    "n8n_workflow_editar_contestacao.json",
    "n8n_workflow_contestacao_claude.json",
]

# Helper: shims do sandbox do n8n. CRITICO: precisa ser SO `const X = ...;`,
# sem `if`/`block` no topo, senao o n8n interpreta o codigo como script global
# e rejeita o `return` que aparece naturalmente nos Code nodes.
#
# `__FETCH` envolve `$helpers.httpRequest` (forma idiomatica do n8n) numa
# interface fetch-like (resp.ok / resp.status / resp.json() / resp.text()).
# Funciona porque `$helpers` esta sempre disponivel no contexto Code node.
PROC_HELPER = (
    "// n8n 2.17.5 JS sandbox shims (process, AbortController, fetch). Tudo em const.\n"
    "const __AC_INIT = (() => { if (typeof globalThis.AbortController === 'undefined') { globalThis.AbortController = class { constructor() { this.signal = undefined; } abort() {} }; } return true; })();\n"
    "const __PROC = (() => { try { return process.env || {}; } catch (_) { return {}; } })();\n"
    "const __HTTP = (() => { try { if ($helpers && $helpers.httpRequest) return $helpers; } catch (_) {} try { if (typeof helpers !== 'undefined' && helpers && helpers.httpRequest) return helpers; } catch (_) {} try { if (this && this.helpers && this.helpers.httpRequest) return this.helpers; } catch (_) {} return null; })();\n"
    "const __FETCH = async (url, opts) => {\n"
    "  opts = opts || {};\n"
    "  const method = opts.method || 'GET';\n"
    "  const headers = opts.headers || {};\n"
    "  let body = opts.body;\n"
    "  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (_) { /* mantem string */ } }\n"
    "  if (!__HTTP) {\n"
    "    try { const r = await fetch(url, opts); return r; } catch (_) {}\n"
    "    throw new Error('http_unavailable: nem $helpers.httpRequest nem fetch global no sandbox');\n"
    "  }\n"
    "  try {\n"
    "    const r = await __HTTP.httpRequest({ url, method, headers, body, json: true, returnFullResponse: true, ignoreHttpStatusErrors: true });\n"
    "    const status = r.statusCode || r.status || 200;\n"
    "    const data = (r.body !== undefined) ? r.body : r;\n"
    "    return {\n"
    "      ok: status >= 200 && status < 300, status,\n"
    "      json: async () => data,\n"
    "      text: async () => (typeof data === 'string' ? data : JSON.stringify(data || {})),\n"
    "    };\n"
    "  } catch (e) {\n"
    "    const status = e.statusCode || e.status || 500;\n"
    "    const msg = (e.message || '').slice(0, 500);\n"
    "    return { ok: false, status, json: async () => ({ error: msg }), text: async () => msg };\n"
    "  }\n"
    "};\n"
)


def strip_old_helpers(js: str) -> str:
    """Remove qualquer trecho de helper que adicionei em tentativas anteriores."""
    # Marcadores de inicio de helpers antigos.
    markers = [
        "// n8n JS Task Runner nao expoe",
        "// n8n 2.17.5 JS sandbox nao expoe",
    ]
    while True:
        start = -1
        for m in markers:
            idx = js.find(m)
            if idx != -1 and (start == -1 or idx < start):
                start = idx
        if start == -1:
            break
        # Encontra o fim do bloco helper. As linhas de helper sao TODAS prefixos
        # consistentes ate uma linha que comeca com algo que nao bate.
        lines = js[start:].split("\n")
        helper_end_local = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Linhas de helper: comentarios, defs __*, blocos de mock, etc.
            if (
                stripped.startswith("//")
                or stripped.startswith("const __")
                or stripped.startswith("if (typeof globalThis")
                or stripped.startswith("if (typeof AbortController")
                or stripped.startswith("globalThis.AbortController")
                or stripped.startswith("};")
                or stripped == ""
                or stripped.startswith("let __")
                or stripped.startswith("return Promise.race")
                or stripped.startswith("const tp = new Promise")
                or stripped.startswith("}")
            ):
                helper_end_local = i + 1
            else:
                break
        if helper_end_local == 0:
            helper_end_local = 1
        end = start + len("\n".join(lines[:helper_end_local]))
        if end < len(js) and js[end] == "\n":
            end += 1
        js = js[:start] + js[end:]
    return js


def fix_node(js: str) -> tuple[str, list[str]]:
    fixes = []
    original = js

    # 1. Limpa helpers antigos.
    js = strip_old_helpers(js)
    if js != original:
        fixes.append("removed old helper(s)")

    # 2. Reverte __PROC residual para process.env (cleanup).
    if "__PROC" in js:
        n = js.count("__PROC")
        js = js.replace("__PROC", "process.env")
        fixes.append(f"reverted __PROC ({n}x) — sera substituido pelo helper novo")

    # 3. Reverte __fetchTO -> fetch (mock AbortController cobre o caso, sem timeout
    #    customizado, mas suficiente porque o readEnv ja tem timeout do tipo Claude).
    if "__fetchTO" in js:
        # Padrao: `await __fetchTO(URL, OPTS, TIMEOUT_VAR)` -> `await fetch(URL, OPTS)`
        # Detecta a string `__fetchTO(` e encontra o ultimo `, X)` antes do `)` que casa.
        def revert_fetchTO(s: str) -> str:
            out = []
            i = 0
            while i < len(s):
                idx = s.find("__fetchTO(", i)
                if idx == -1:
                    out.append(s[i:])
                    break
                out.append(s[i:idx])
                # Encontra o ) que casa com o ( de __fetchTO
                paren_start = idx + len("__fetchTO")
                depth = 0
                j = paren_start
                while j < len(s):
                    if s[j] == "(":
                        depth += 1
                    elif s[j] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                inner = s[paren_start + 1:j]
                # `inner` eh `URL, OPTS, TIMEOUT_VAR`. Remove o ultimo argumento (timeout).
                # Encontra a ultima virgula em depth=0
                last_comma = -1
                d = 0
                for k, ch in enumerate(inner):
                    if ch == "(" or ch == "{" or ch == "[":
                        d += 1
                    elif ch == ")" or ch == "}" or ch == "]":
                        d -= 1
                    elif ch == "," and d == 0:
                        last_comma = k
                if last_comma != -1:
                    inner_clean = inner[:last_comma].rstrip()
                else:
                    inner_clean = inner
                out.append(f"fetch({inner_clean})")
                i = j + 1
            return "".join(out)
        n_revert = js.count("__fetchTO(")
        js = revert_fetchTO(js)
        fixes.append(f"__fetchTO -> fetch ({n_revert}x — timeout removido, mock AC cobre)")

    # 4. Substitui process.env -> __PROC (so no codigo do node, helper sera prepend).
    if "process.env" in js:
        n = js.count("process.env")
        js = js.replace("process.env", "__PROC")
        fixes.append(f"process.env -> __PROC ({n}x)")

    # 4b. Substitui fetch( -> __FETCH( (sandbox bloqueia fetch global).
    # Usa regex para nao casar `__FETCH(` (ja substituido) ou `await fetch(` ja em outras posicoes.
    fetch_pattern = re.compile(r"\bfetch\s*\(")
    n_fetch = len(fetch_pattern.findall(js))
    if n_fetch > 0:
        js = fetch_pattern.sub("__FETCH(", js)
        fixes.append(f"fetch( -> __FETCH( ({n_fetch}x)")

    # 5. So aplica fix se realmente precisava.
    needs_helper = (
        "__PROC" in js
        or "new AbortController" in js
        or "AbortController" in js
    )
    if not needs_helper:
        return original, []

    # 6. Prepend helper limpo.
    new_js = PROC_HELPER + js
    fixes.append("prepended PROC_HELPER")
    return new_js, fixes


def fix_workflow(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        wf = json.load(f)

    relatorio = {"file": path.name, "nodes": []}
    altered = False
    for node in wf.get("nodes", []):
        params = node.get("parameters") or {}
        js = params.get("jsCode")
        if not js:
            continue
        new_js, fixes = fix_node(js)
        if fixes:
            params["jsCode"] = new_js
            relatorio["nodes"].append((node["name"], fixes))
            altered = True

    if altered:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)

    return relatorio


for nome in ARQUIVOS:
    rel = fix_workflow(DOCS / nome)
    print(f"\n{rel['file']}:")
    for n, fxs in rel["nodes"]:
        print(f"  - {n}")
        for fx in fxs:
            print(f"      * {fx}")
