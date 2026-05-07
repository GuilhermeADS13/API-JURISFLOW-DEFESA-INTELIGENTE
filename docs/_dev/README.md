# `_dev/` — Scripts de manutenção (não versionados em produção)

Esta pasta contém utilitários de desenvolvimento que **não fazem parte do produto**.
Não são importados pelo backend nem pelo frontend.

## `_fix_workflows.py`

Script Python que aplica patches de compatibilidade nos 3 workflows n8n
(`n8n_workflow_contestar_por_peticao.json`, `n8n_workflow_editar_contestacao.json`,
`n8n_workflow_contestacao_claude.json`) para fazê-los rodar no sandbox JS do
**n8n 2.17.5 + JS Task Runner externo**, que é mais restritivo que o sandbox antigo.

### Bugs cobertos

| Symptom | Causa | Patch aplicado |
|---|---|---|
| `process is not defined` | sandbox não expõe `process` global | substitui `process.env` por `__PROC` (try/catch) |
| `AbortController is not defined` | sandbox não expõe `AbortController` | mock via `globalThis.AbortController` (no-op) |
| `Illegal return statement` | sandbox detecta `if/block` no topo e roda como script global | helper usa só `const X = ...;` sem `if` no topo |
| `fetch is not defined` | sandbox não expõe `fetch` | substitui `fetch(` por `__FETCH(` que tenta `globalThis.fetch.bind(globalThis)` |

### Como usar

```bash
PYTHONIOENCODING=utf-8 python docs/_dev/_fix_workflows.py
```

Edita os 3 arquivos JSON in-place. Idempotente: detecta helpers antigos,
remove e reaplica o atual. Depois de rodar:

```bash
docker exec autojuri_n8n sh -c '
  n8n import:workflow --input=/data/workflows/n8n_workflow_contestar_por_peticao.json
  n8n import:workflow --input=/data/workflows/n8n_workflow_editar_contestacao.json
  n8n import:workflow --input=/data/workflows/n8n_workflow_contestacao_claude.json
  n8n update:workflow --id=WF_AUTOJURI_CONTESTAR_POR_PETICAO --active=true
  n8n update:workflow --id=WF_AUTOJURI_EDITAR_CONTESTACAO --active=true
  n8n update:workflow --id=WF_AUTOJURI_CONTESTACAO_CLAUDE --active=true
'
docker restart autojuri_n8n
```

E testar:

```bash
curl -s -X POST http://localhost:5678/webhook/contestar-por-peticao \
  -H "Content-Type: application/json" \
  -d '{"texto_peticao":"PETICAO INICIAL... (>=50 chars)","tipo_acao_hint":"Trabalhista","usuario_id":"t"}'
```

Resposta com `engine_ia.provider == "claude"` significa pipeline OK.
`engine_ia.provider == "fallback"` + `api_error: "<algo> is not defined"` indica
que ainda há um global bloqueado pelo sandbox que precisa ser shimmed.

### Status (2026-05-06)

Sessão parou no patch `__FETCH`. Os JSONs em `docs/` estão com o patch aplicado
mas **não foram re-importados nem testados** após a substituição `fetch -> __FETCH`.
Próxima sessão: re-importar via comando acima e testar com curl.
