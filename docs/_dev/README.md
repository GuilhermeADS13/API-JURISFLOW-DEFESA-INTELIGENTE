# `_dev/` — Scripts de manutenção (não fazem parte do produto)

Utilitários de desenvolvimento que **não são importados pelo backend nem pelo frontend**.

## Ativos (scripts em uso)

### Patches do workflow n8n

Cada um adiciona/altera um node ou regra do workflow `contestar-por-peticao` de forma idempotente. Detectam marker e não reaplicam:

| Script | O que faz | PR |
|---|---|---|
| `_patch_detector_contradicoes.py` | Adiciona node Haiku entre Self-Correction e Responder | PR12 #10 |
| `_patch_extrator_area_juridica.py` | Faz Extrator pedir `area_juridica` no JSON | PR13 #B1 |
| `_patch_legislacao_node.py` | Adiciona node "Buscar Legislacao Aplicavel" + injeta no SYSTEM | PR13 #B3 |
| `_patch_documentos_anexos.py` | Adiciona `documentos_anexos[]` no JSON da minuta | PR14 |
| `_patch_tipo_canonico_anexos.py` | Adiciona dica de nomenclatura canônica no SYSTEM | PR15 |

Após rodar qualquer patch, re-importe via:

```powershell
docs/_dev/reimport_workflows.ps1
```

### Operações

| Script | Função |
|---|---|
| `reimport_workflows.ps1` | Re-importa os 3 workflows JSON via n8n REST API (autentica com `N8N_API_KEY` do `Backend/.env`) |
| `smoke_test_agente_claude.ps1` | Smoke test ponta-a-ponta do agente Claude via webhook |

### Dependências

`package.json` + `package-lock.json` — deps Node dos scripts (`pdf2image`, etc.). Instalar com `npm install` dentro de `_dev/`.

## `_archived/` — Scripts one-shot já rodados

Preservados em git para rastreabilidade. Não usar mais (a maioria foi migração ou geração de PDF acadêmico):

- `_fix_workflows.py`, `_update_rag_node.py` — migrações pontuais do sandbox n8n
- `backfill_embeddings.py`, `update_exemplar_id18.py` — backfills de dados
- `gerar_pdf*.py`, `gerar_planilha_custos.py`, `gerar_relatorio_pdf.py`, `gerar_riscos_prioridades_pdf.py`, `converter_para_pdf.py` — geraram PDFs da pasta `docs/historico/`
- `capturar_screenshots.mjs` + `gerar_entrega_final.ps1` — pipeline de entrega acadêmica
- `start-stack.cmd` / `start-stack.ps1` — substituídos pelas skills `/ligarserver` e `/desligarserver`
- `n8n_workflow_v3_legacy.json` — snapshot de workflow legado
