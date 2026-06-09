# Plano de Implementação — Edição cirúrgica de .docx + Atualização do agente IA

Data: 2026-04-29
Continua a [REVISAO_2026-04-29.md](REVISAO_2026-04-29.md)

## Contexto

Duas frentes complementares decididas com o usuário:

**Fase 1 — Edição cirúrgica de .docx**: o workflow `contestacao-claude` atual gera minuta nova do zero (em `.txt`). Mas o caso de uso real do screenshot é **outro**: usuário envia um `.docx` de contestação já redigida + instruções "substitua o nome X por Y, o número Z por W" e recebe o `.docx` editado, formatação preservada, sem usar LibreOffice. Isso vira um **workflow paralelo** (não substitui o atual).

**Fase 2 — "Treinar" o agente atual**: como Claude não aceita fine-tuning, "treinar" na prática significa melhorar o que entra no prompt. As 3 estratégias escolhidas:
- Prompt mais especializado + 2-3 few-shot examples de contestações que saíram boas
- RAG do histórico do escritório melhor: 5-10 casos (em vez de 3), scoring por similaridade real (não só `tipo_acao`), incluir trechos das minutas que deram certo
- Feedback loop: advogado avalia a minuta ("útil/não útil"), sistema usa o feedback para ponderar quais defesas anteriores aparecem no contexto

**Fora deste plano**: integração Jusbrasil/STJ (decisão do usuário — fica para depois).

---

## Fase 1 — Edição cirúrgica de .docx

### 1.1 Objetivo

Endpoint `POST /api/editar-contestacao` que aceita:
- `arquivo_base_conteudo_base64`: o `.docx` modelo
- `arquivo_base_nome`, `arquivo_base_mime_type`, `arquivo_base_tamanho_bytes`: metadados (já validados em `Processo`)
- `nome_novo`: string (ex: "Erica Cavalcante de Oliveira") — opcional
- `numero_processo_novo`: CNJ (ex: "0000057-64.2026.5.06.0341") — opcional
- `valor_causa_novo`: string monetária (ex: "27.598,41") — opcional

Retorna:
- `arquivo_editado_base64`: `.docx` editado
- `arquivo_editado_nome`: `Contestacao_editada_<numero_novo>.docx`
- `relatorio`: lista de bullets descrevendo cada substituição (formato do screenshot)
- `status`: `ok` / `erro_validacao` / `erro`

Restrição: **não usar LibreOffice** (sem `soffice --convert-to`).

### 1.2 Arquitetura

```
Frontend (form)
  ↓ POST /api/editar-contestacao  (FastAPI)
  | body: { arquivo_base64, nome_novo, numero_processo_novo, valor_causa_novo }
  ↓
Backend FastAPI — App/routes/edicao.py (novo)
  ├─ valida payload (reusa validacoes de Processo p/ arquivo)
  ├─ POST n8n /webhook/editar-contestacao (novo workflow)
  │   └─ node Code 1: extrai texto do .docx (usa python-docx via subprocess
  │       OU recebe texto extraido pelo backend)
  │   └─ node Code 2: chama Claude com instrucao para listar antigo<->novo
  │   └─ Webhook responde com pares de substituicao + campos_ausentes
  ├─ aplica substituicao com python-docx (preserva runs, estilos)
  ├─ valida ocorrencias_reais == ocorrencias_esperadas
  ├─ persiste em contestacoes (status='ok'/'erro_validacao')
  └─ retorna DOCX editado em base64 + relatorio
```

Por que **python-docx no backend** e não no n8n: `.docx` é ZIP+XML; substituir string em `word/document.xml` quebra quando o texto cruza fronteiras de runs (`<w:r><w:t>`). `python-docx` resolve isso. n8n via JS exigiria nova lib + reconfigurar a imagem — esforço maior.

Por que **Claude no n8n e não no backend**: já temos o canal n8n configurado (`ANTHROPIC_API_KEY` no container, prompt-caching, fallback determinístico). Reusar mantém uma fonte única de configuração de IA.

### 1.3 Mudanças por arquivo

| Arquivo | Tipo | O que muda |
|---|---|---|
| `Backend/requirements.txt` | edit | adicionar `python-docx==1.1.2` |
| `Backend/App/models/edicao.py` | **novo** | schema Pydantic `EdicaoContestacao` (validação dos 3 campos novos + arquivo) |
| `Backend/App/services/docx_editor.py` | **novo** | `aplicar_substituicoes(docx_bytes, pares) -> (docx_bytes_editado, ocorrencias_reais)`; lida com runs adjacentes |
| `Backend/App/services/n8n_service.py` | edit | adicionar `enviar_para_n8n_edicao(payload)` apontando para `N8N_EDICAO_WEBHOOK_URL` (variavel nova) |
| `Backend/App/routes/edicao.py` | **novo** | rota `POST /api/editar-contestacao` (rate limit 5/min, requer auth) |
| `Backend/main.py` | edit | `app.include_router(edicao.router, prefix="/api", tags=["Edicao"])` |
| `Backend/App/database.py` | edit | nova tabela `edicoes_contestacao` ou reusar `contestacoes` com `tipo_operacao` (editar/gerar) — decidir |
| `docs/n8n_workflow_editar_contestacao.json` | **novo** | workflow n8n: Webhook → Code (extrair texto via libreria interna n8n OU receber texto pelo body) → Code (chamar Claude) → Responder |
| `docker-compose.yml` | edit | adicionar `N8N_EDICAO_WEBHOOK_URL=http://n8n:5678/webhook/editar-contestacao` |
| `.env.example` | edit | documentar `N8N_EDICAO_WEBHOOK_URL` |
| `Backend/tests/test_routes_edicao.py` | **novo** | happy-path, campo ausente, ocorrencias divergentes |
| `Backend/tests/test_docx_editor.py` | **novo** | substituicao em runs simples, runs fragmentados, multiplas ocorrencias |
| `docs/AGENTE_IA_AUTOJURI.md` | edit | documentar o segundo agente |

### 1.4 Schema do prompt do agente de edição

```
SYSTEM:
Voce eh um agente de edicao ciruurgica de documentos juridicos. Recebe:
1. Texto extraido de uma contestacao (.docx).
2. Campos novos: nome, numero_processo, valor_causa (qualquer pode ser null).

Sua tarefa: identificar a ocorrencia principal de cada campo no texto e retornar
em JSON estrito (sem markdown), com a estrutura:

{
  "substituicoes": [
    { "campo": "nome",            "antigo": "...", "novo": "...", "ocorrencias_esperadas": N },
    { "campo": "numero_processo", "antigo": "...", "novo": "...", "ocorrencias_esperadas": N },
    { "campo": "valor_causa",     "antigo": "...", "novo": "...", "ocorrencias_esperadas": N }
  ],
  "campos_ausentes": ["valor_causa"]
}

REGRAS:
- Se um campo novo foi pedido mas nao existe no texto, inclua em "campos_ausentes"
  e NAO gere substituicao para ele.
- "antigo" deve ser uma string EXATA do texto (case-sensitive).
- NAO invente. NAO faca outras alteracoes.
- "ocorrencias_esperadas" eh o numero exato de vezes que "antigo" aparece.
- Para nome: identifique o nome da parte (Reclamado/a, Reu, Contestante).
- Para numero_processo: identifique formato CNJ (XXXXXXX-XX.XXXX.X.XX.XXXX).
- Para valor_causa: identifique valor monetario (R$ X.XXX,XX) tipicamente
  apos "valor da causa" ou similar.

USER:
TEXTO_DOCUMENTO:
<<<conteudo extraido pelo python-docx>>>

CAMPOS_NOVOS:
{ "nome": "...", "numero_processo": "...", "valor_causa": "..." }
```

Parâmetros recomendados (mais conservadores que o workflow atual): **temperatura 0.0**, `max_tokens=1500`, `response_format={"type":"json_object"}` se a versão da API suportar (caso contrário, parser via `stripFences` reusado do node atual).

### 1.5 Validação pós-edição (no backend)

Para cada substituição recebida do Claude:
1. Contar ocorrências reais no `.docx` extraído.
2. Se `ocorrencias_reais != ocorrencias_esperadas` ou `0`: **abortar** com 422 e diff explícito (impede substituição parcial silenciosa que troque a ocorrência errada).
3. Aplicar com `python-docx`, agrupando runs adjacentes quando o `antigo` cruzar `<w:r>` boundaries.
4. Salvar num `BytesIO`, base64-encode, retornar.
5. Montar relatório no formato do screenshot (bullets em PT, com `**negrito**` no valor novo).

### 1.6 Plano de testes

- **Unitário** `test_docx_editor.py`: 3 fixtures `.docx` (run simples, run fragmentado, múltiplas ocorrências) + assertions de bytes equivalentes em estilo
- **Integração** `test_routes_edicao.py`: mock `enviar_para_n8n_edicao`, valida happy-path + 422 quando ocorrências divergem + 401 sem auth
- **Regressão**: rodar suite completa antes/depois (`pytest`)

### 1.7 Rollout

1. PR 1: `python-docx` + `docx_editor.py` + tests unitários (deploy seguro, sem rota nova)
2. PR 2: model + route + n8n_service helper, **rota retorna 503 enquanto workflow n8n não existir**
3. PR 3: workflow n8n + ativação da rota
4. Smoke test em staging com o documento `.docx` real do screenshot

### 1.8 Estimativa
- python-docx + tests: 1 dia
- Backend route + service: 1 dia
- Workflow n8n + prompt + integração: 1 dia
- Smoke test + ajustes: 0.5 dia
- **Total: ~3.5 dias**

---

## Fase 2 — Atualização do agente IA atual (`contestacao-claude`)

Objetivo: melhorar a qualidade da minuta gerada **sem** mudar o contrato externo (mesmo webhook, mesmo formato de resposta), via 3 frentes:

### 2.1 Prompt + few-shot examples

**Onde**: node `Agente IA Claude Anthropic` em [docs/n8n_workflow_contestacao_claude.json](n8n_workflow_contestacao_claude.json), variável `SYSTEM_PROMPT`.

**Mudanças no system prompt**:
- Bloco "PADRÃO DE QUALIDADE" listando o que foi aprendido das revisões humanas (linguagem formal, cita CLT/CC sem inventar artigo, evita superlativos)
- Bloco "EXEMPLOS DE TESES BOAS" com 2-3 exemplos `tipo_acao → tese_central → fundamentos` (extraídos das contestações com feedback positivo do escritório)
- Bloco "ANTIPADRÕES" com o que o agente deve evitar (tese genérica demais, citação numérica de jurisprudência inventada, linguagem informal)

Os few-shots ficam no `system` (cacheável via `prompt-caching-2024-07-31` que já está ativo) — assim o custo extra de tokens é amortizado entre chamadas.

**Onde os exemplos vêm**: nova tabela `contestacoes_exemplares` no Postgres com 2-3 minutas escolhidas a dedo pelo escritório (não vem do RAG dinâmico — é curadoria manual). Schema: `id`, `tipo_acao`, `tese_central`, `fundamentos_resumo`, `nota_qualidade`, `criado_em`.

**Como populamos**: endpoint admin `POST /api/admin/exemplares` (proteção: lista de e-mails admin em env var) ou seed inicial via SQL.

### 2.2 RAG do histórico melhor

**Estado atual** ([docs/n8n_workflow_contestacao_claude.json](n8n_workflow_contestacao_claude.json), node `Buscar Defesas Anteriores Supabase`):
```
GET /rest/v1/contestacoes
  ?status=eq.ok
  &tipo_acao=eq.{tipo}
  &numero_processo=neq.{numero}
  &order=criado_em.desc
  &limit=5
```
Limite 5, ordena por data, filtra por `tipo_acao` exato. Daí passa só os 3 primeiros para o prompt.

**Mudanças propostas**:

a) **Ampliar para 10 + scoring por similaridade real**: depois de buscar 10 do mesmo `tipo_acao`, scorar cada um pelo **TF-IDF cosseno** entre `fatos` do caso atual e `fatos` do caso passado (cálculo simples em JS no node Code, sem dependência externa) e selecionar os top-3 com maior score. Casos com score < 0.1 são descartados (relevância baixa demais).

b) **Trechos das minutas que tiveram sucesso**: hoje passamos `tese_central`, `resumo_estrategico`, `fatos_resumo`, `pedido_autor_resumo`, `riscos`. Adicionar `fundamentos_curtos` (primeiros 1500 chars do `n8n_resposta.minuta.fundamentos`) — o modelo aprende o estilo de fundamentação do escritório, não só a tese.

c) **Dar peso ao feedback** (depende do 2.3): score final = `0.6 * similaridade_tfidf + 0.4 * nota_feedback_normalizada`. Casos sem feedback usam `0.5` neutro.

**Onde**: mesmo node `Buscar Defesas Anteriores Supabase`. Funções TF-IDF e cosseno em puro JS — código compacto, sem deps.

### 2.3 Feedback loop

**Coleta**:
- Após o frontend exibir a minuta, mostrar 2 botões: "Foi útil" / "Não foi útil" (e opcionalmente "Comentário")
- Endpoint novo `POST /api/contestacoes/{id_caso}/feedback` no backend, body: `{ util: bool, comentario?: str }`
- Auth obrigatória (mesmo `get_authenticated_user`); só o usuário dono do caso pode mandar feedback

**Persistência**:
- Nova coluna em `contestacoes`: `feedback_util BOOLEAN`, `feedback_comentario TEXT`, `feedback_em TIMESTAMPTZ`
- Migration via `ALTER TABLE ADD COLUMN IF NOT EXISTS` em `database.py:init_db()`

**Uso no RAG (2.2c)**:
- `nota_feedback_normalizada`: `feedback_util=true` → 1.0, `false` → 0.0, `NULL` → 0.5
- Casos com `feedback_util=false` ainda podem aparecer (até pra o modelo aprender o que evitar), mas com peso menor

### 2.4 Mudanças por arquivo (Fase 2)

| Arquivo | Tipo | O que muda |
|---|---|---|
| `docs/n8n_workflow_contestacao_claude.json` | edit | system prompt expandido (few-shot, antipadrões, qualidade); node `Buscar Defesas` com TF-IDF + scoring por feedback; node `Agente Claude` recebe `fundamentos_curtos` |
| `Backend/App/database.py` | edit | `init_db` adiciona colunas `feedback_util`, `feedback_comentario`, `feedback_em` em `contestacoes`; nova função `salvar_feedback(caso_id, util, comentario, usuario_id)`; nova função `get_contestacoes_exemplares(tipo_acao)` para o seed |
| `Backend/App/database.py` | edit | nova tabela `contestacoes_exemplares` no `init_db` |
| `Backend/App/models/feedback.py` | **novo** | schema Pydantic `FeedbackContestacao` |
| `Backend/App/routes/contestacao.py` | edit | nova rota `POST /contestacoes/{id_caso}/feedback` |
| `Backend/tests/test_routes_feedback.py` | **novo** | happy-path, sem auth, caso de outro usuário |
| `docs/contestacoes_exemplares_seed.sql` | **novo** | 2-3 INSERTs com minutas selecionadas pelo escritório |
| `docs/AGENTE_IA_AUTOJURI.md` | edit | seção nova "Como o agente aprende: prompt + RAG + feedback" |

### 2.5 Plano de testes (Fase 2)

- **Unitário**: TF-IDF + cosseno isolados (testar com casos sintéticos)
- **Integração**: rota de feedback, leitura de exemplares
- **End-to-end manual**: gerar 3 contestações antes/depois das mudanças com o mesmo input e comparar qualidade subjetivamente (advogado avalia)

### 2.6 Rollout (Fase 2)

1. PR 1: migrations (colunas de feedback, tabela `contestacoes_exemplares`) + rota de feedback (sem usar ainda no agente)
2. PR 2: seed inicial de `contestacoes_exemplares` (2-3 SQL INSERTs revistos pelo escritório)
3. PR 3: workflow n8n com prompt expandido + few-shot via `contestacoes_exemplares`
4. PR 4: workflow n8n com TF-IDF + scoring por feedback
5. **Soak**: 2 semanas observando feedback do escritório antes de chamar de "concluído"

### 2.7 Estimativa
- Migration + rota feedback + tests: 1 dia
- Seed exemplares + curadoria com escritório: 1 dia (grande parte do escritório, não dev)
- Prompt expandido + few-shot integration: 1 dia
- TF-IDF + scoring no n8n + tests: 1.5 dia
- Soak + ajustes finos: 2 semanas (passivo)
- **Total dev: ~4.5 dias** + 2 semanas de observação

---

## Ordem de execução sugerida

1. **Fase 1 PR 1-2** (python-docx + route shell) — desbloqueia o caso de uso real do screenshot
2. **Fase 2 PR 1** (migrations + rota feedback) — pode ir em paralelo, é independente
3. **Fase 1 PR 3** (workflow n8n de edição) — fecha a feature do .docx
4. **Fase 2 PR 2-4** (seed, prompt, RAG melhorado) — sequencial, cada um se beneficia do anterior
5. **Soak de 2 semanas** com feedback do escritório
6. Revisão e ajustes finais

## Riscos e mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Substituição cirúrgica em runs fragmentados quebra o `.docx` | Média | Testes unitários extensivos com fixtures reais; abortar se ocorrências divergem |
| Claude retorna "antigo" que não existe exatamente no texto (alucina espaço/case) | Alta | Validação de ocorrências antes de aplicar; se divergir, retornar 422 com diff |
| Few-shot examples no prompt aumentam custo de tokens | Baixa | Prompt-caching já ativo; após 1ª chamada, custo extra é mínimo |
| TF-IDF em JS no n8n fica lento com 100+ casos | Baixa | Limitar busca inicial a 20; cálculo TF-IDF é O(n·m) e n=20 é trivial |
| Feedback loop introduz viés (poucos casos com feedback "útil" cedo) | Média | Score neutro 0.5 para `NULL`; só aplicar peso quando o escritório acumular ≥30 feedbacks |

## Dependências externas

- Aprovação do escritório para curadoria dos `contestacoes_exemplares` (Fase 2 PR 2)
- Rotação da chave Anthropic (item ainda pendente da revisão) — não bloqueia, mas precisa antes de prod
- Decisão se vai criar tabela `edicoes_contestacao` ou reusar `contestacoes` com `tipo_operacao` (Fase 1) — recomendo **reusar** para simplificar dashboard

## Itens fora deste plano

- Integração Jusbrasil/STJ (decisão do usuário — fase futura)
- Migração para Argon2id (segurança, baixa prioridade — PBKDF2 600k já é OWASP-compliant após esta revisão)
- Refator do `requirements.txt` para pip-tools (médio, qualidade-de-vida)

## Verificação ao terminar

- [ ] `POST /api/editar-contestacao` retorna `.docx` editado para o input do screenshot e o relatório de bullets bate com o ChatGPT do print
- [ ] Workflow `editar-contestacao` ativo no n8n e MCP `n8n-autojuri` lista 2 workflows
- [ ] Migrations aplicadas, `contestacoes_exemplares` populada com ≥2 exemplos
- [ ] Rota de feedback aceita POST e a coluna preenche corretamente
- [ ] Suite de testes verde (`pytest` 100%)
- [ ] Após 2 semanas de soak, ≥10 feedbacks coletados e o RAG já está usando-os no scoring
