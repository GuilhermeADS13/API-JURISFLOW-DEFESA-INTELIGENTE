# Spec 01 — Backend FastAPI

**Escopo:** APIs HTTP, autenticação, persistência, orquestração com n8n, geração de DOCX coordenada pelo backend.
**Não cobre:** workflows n8n internos (spec 03), RAG/embeddings em profundidade (spec 04), frontend (spec 02), Docker (spec 05), LGPD (spec 06).

---

## 1. Inventário atual

**Stack:** Python 3.12 + FastAPI 0.116.1 + uvicorn 0.35.0 + Pydantic 2.13.3 + psycopg2-binary 2.9.12 + slowapi 0.1.9 + python-docx 1.1.2 + pypdf 4.3.1 + sentence-transformers 3.x + pytesseract 0.3.13. Total ~6500 LoC em `Backend/App/`. 269 testes pytest passando.

### 1.1 Routes (`Backend/App/routes/`)
| Arquivo | Linhas | Endpoints expostos |
|---|---:|---|
| `contestacao.py` | 213 | `POST /contestacao`, `GET /contestacoes`, `GET /contestacoes/{id}` |
| `contestacao_peticao.py` | 725 | `POST /contestar-por-peticao`, `POST /contestacoes/{id}/confirmar-extracao`, `GET /contestacoes/{id}/baixar`, `PATCH /contestacoes/{id}/minuta` |
| `edicao.py` | 297 | `POST /contestacoes/{id}/editar`, `POST /aplicar-edicao` |
| `feedback.py` | 125 | `POST /feedback`, `GET /feedback` |
| `rag.py` | 162 | `GET /rag/exemplares`, debug endpoints |
| `suporte.py` | 44 | `POST /suporte` |
| `usuario.py` | 169 | `POST /cadastro`, `POST /login`, `POST /logout`, `GET /me` |

### 1.2 Services (`Backend/App/services/`)
| Arquivo | Linhas | Responsabilidade |
|---|---:|---|
| `auth_service.py` | 73 | Login/sessão local legado (pré-Supabase) |
| `contestacao_docx_builder.py` | 654 | Render DOCX (com modelo + programático) com renderer Markdown próprio |
| `diff_minuta.py` | 134 | Diff entre minuta original IA vs editada humano (golden dataset) |
| `docx_editor.py` | 156 | Edição supervisionada da minuta |
| `embedding_service.py` | 224 | sentence-transformers MiniLM (384-dim), similarity search via pgvector |
| `n8n_service.py` | 275 | HTTP client para webhooks n8n, retry, mapping de erros |
| `peticao_extractor.py` | 640 | Extrai texto de PDF (pypdf → OCR fallback), consolida anexos |
| `suporte_email_service.py` | 153 | Envio de email do formulário de suporte |

### 1.3 Models (`Backend/App/models/`)
| Arquivo | Linhas | Modelo principal |
|---|---:|---|
| `contestacao_por_peticao.py` | 260 | `ContestacaoPorPeticao`, `ConfirmacaoExtracao`, `MinutaEditada` |
| `edicao.py` | 160 | Pydantic models de edição |
| `n8n_response.py` | 26 | Genérico (`Any | None`, `extra=ignore`) |
| `processo.py` | 148 | Modelo de processo |
| `usuario.py` | 164 | Cadastro/login |
| `suporte.py` | 74 | Form de suporte |
| `exemplar.py` | 30 | Exemplar curado RAG |
| `feedback.py` | 28 | Feedback do advogado |

### 1.4 Infraestrutura
- `database.py` (1275 linhas) — conexões psycopg2, queries, save/get/list de contestações, sessões, embeddings.
- `security.py` (269 linhas) — autenticação dupla: sessão local legada + bearer token Supabase com cache TTL 30s.
- `limiter.py` (37 linhas) — slowapi com chave por usuário/IP.

---

## 2. Pontos fortes

1. **Separação por fluxo bem desenhada em `contestacao_peticao.py`** — helpers privados (`_decodificar_*`, `_chamar_n8n_peticao`, `_montar_save_payload`, `_fluxo_ok`, `_fluxo_revisao_humana`) mantêm o endpoint principal abaixo de 40 linhas e cada helper testável isoladamente (`Backend/App/routes/contestacao_peticao.py:117-258`).
2. **Embedding em thread daemon não bloqueia resposta** — `_disparar_embedding` em `contestacao_peticao.py:101` desacopla persistência da resposta, com try/except de logging que não derruba a thread.
3. **Cache de validação Supabase com hash SHA-256** — `security.py:48-77` cacheia tokens com TTL 30s + eviction por tamanho (max 500), nunca armazenando o token em claro.
4. **Mapping consistente de exceções para HTTP status** — `_chamar_n8n_peticao`, `_persistir_contestacao`, `_extrair_texto_peticao` normalizam falhas para 422/500/502 com `from error` para preservar traceback.
5. **PR5 Human-in-the-Loop** — fluxo de baixa confiança (`< 0.7`) NÃO gera DOCX, marca `requer_revisao_humana`, retorna preview da minuta + dados extraídos para revisão. Quando humano confirma, n8n bypassa o Extrator (economia de 1 chamada Claude).
6. **`MinutaEditada` patch parcial sincronizado com tupla `_CAMPOS_MINUTA_EDITAVEL`** (`contestacao_peticao.py:707`) — fácil estender campo editável sem ramificar.

---

## 3. Riscos e bugs latentes

| # | Sev | File:line | Bug | Impacto |
|---|---|---|---|---|
| R1 | 🔴 | `database.py` (1275 linhas) | Arquivo monolítico — quase 200 funções num único módulo | Refactor difícil; PRs colidem; teste de uma query exige import grande |
| R2 | 🔴 | `peticao_extractor.py` | Sem timeout explícito no OCR (pytesseract). PDF malicioso/digitalizado de 50 páginas trava worker uvicorn | DoS via upload; bloqueio do event loop |
| R3 | 🔴 | `contestacao_peticao.py:81-111` (thread daemon) | Thread daemon de embedding morre silenciosamente no shutdown → embedding nunca salvo | Inconsistência: contestação salva sem embedding; RAG fica menor que o esperado |
| R4 | 🟡 | `security.py:65-77` (eviction simples) | Eviction só remove expirados, não LRU. Em ataque de tokens distintos, cache enche de inválidos antes da expiração | Memória cresce até `_SUPABASE_CACHE_MAX_ENTRIES`, latência aumenta com colisão |
| R5 | 🟡 | `contestacao_peticao.py:585-596` (download) | `dados_extraidos.setdefault(campo, contestacao[campo])` muta dict in-place do JSON do n8n_resposta | Se o mesmo objeto for reusado em logging posterior, dados pessoais vazam para campos errados |
| R6 | 🟡 | `n8n_service.py` | Sem circuit breaker — falhas consecutivas seguem batendo no n8n por 30s timeout cada | Cascata: backend trava porta + memória ao acumular conexões em retry |
| R7 | 🟡 | `contestacao_peticao.py:586` | `minuta_json_editada` pode estar parcial (PATCH parcial). Fallback para `minuta` original mascara perda de edição | Usuario perde edição se PATCH falhou silenciosamente antes |
| R8 | 🟡 | `database.py` (queries) | Conexões psycopg2 sem pool centralizado → cada call abre conexão? Verificar | Latência por handshake; esgotamento de conexões em pico |
| R9 | 🟢 | `contestacao_peticao.py:93` | `except Exception as err` no embedding background — log mas não métrica | Falhas silenciosas em produção; sem alerta |
| R10 | 🟢 | `contestacao_peticao.py:553-605` (`/baixar`) | Status hardcoded `!= "ok"` — qualquer outro status (incluindo novos no futuro) bloqueia download | Acoplamento entre enum implícito de status e regra de negócio |

**Fix sugeridos (resumo):**
- **R1**: dividir `database.py` em `db/sessions.py`, `db/contestacoes.py`, `db/embeddings.py`, `db/usuarios.py`. PR de pura movimentação, sem mudar comportamento.
- **R2**: envolver OCR em `concurrent.futures.ThreadPoolExecutor` com `future.result(timeout=60)`. PDFs maiores → 422 com mensagem clara.
- **R3**: trocar thread daemon por fila persistente (Redis + RQ) ou tabela `embeddings_pendentes` consumida por worker. Resiliente a restart.
- **R4**: trocar dict simples por `cachetools.TTLCache` com LRU (já testado).
- **R5**: `dict(dados_extraidos)` antes do setdefault (copy defensiva).
- **R6**: introduzir `pybreaker` ou implementar circuit breaker simples (5 falhas em 60s → open por 30s).
- **R8**: confirmar uso de `psycopg2.pool.ThreadedConnectionPool` em `database.py` (auditar `get_conn`). Se não existir, adicionar pool com min=2 max=10.

---

## 4. Oportunidades de refactor

1. **Extrair `pipeline_contestacao_peticao` como service** — `_fluxo_ok` e `_fluxo_revisao_humana` em `contestacao_peticao.py:382-466` orquestram regra de negócio que está acoplada à route. Mover para `services/pipeline_contestacao.py`. Benefício: testável sem TestClient; route fica thin controller.
2. **Unificar `montar_docx_com_modelo` + `montar_docx_programatico` por strategy** — `contestacao_docx_builder.py` tem 2 caminhos divergentes. Criar `class DocxBuilder` com `strategy: TemplateStrategy | ProgramaticStrategy`. Benefício: novo backend (LaTeX, HTML→PDF) sem mexer na route.
3. **Centralizar `_coerce_float`, `_join_pedidos`, `_montar_nome_saida` em `utils/`** — usados em múltiplas routes, hoje copiados. Benefício: única fonte de verdade.
4. **Substituir `from App.services.embedding_service import gerar_embedding` lazy por DI** — hoje import dentro de função para evitar carregar sentence-transformers em startup. Trocar por `Depends(get_embedding_service)` que late-loads via cache. Benefício: testável (injeta fake) sem monkey-patch.
5. **Tipos do `database.py` retornam `dict` cru** — modelos pydantic não usados na camada de DB. Introduzir TypedDict ou pydantic interno para serializar resultado. Benefício: autocomplete, erro em tempo de import quando schema muda.
6. **`payload_n8n: dict` poderia ser pydantic** — em `contestacao_peticao.py:334`. Hoje qualquer typo na chave passa silencioso. Criar `N8NPayloadPeticao(BaseModel)`. Benefício: serialização validada.

---

## 5. Specs novos (features e melhorias)

### 5.1 Idempotency-Key em POSTs caros 🅢🅼
**Motivação:** retry de cliente no `POST /contestar-por-peticao` gera 2× chamada Claude (R$ 1-3 cada). Já há janela de timeout 9min onde isso acontece.
**Escopo:** header `Idempotency-Key`, tabela `idempotency_keys (key, usuario_id, response_body, expires_at)`, middleware em FastAPI.
**Critério aceite:** mesmo key + mesmo usuario_id em 24h → retorna response cacheado, sem reprocessar.
**Esforço:** M (3-5 dias).

### 5.2 Healthcheck profundo 🅢
**Motivação:** hoje `/health` retorna `{"status": "healthy"}` sem checar dependências. Container fica "healthy" mesmo com DB caído.
**Escopo:** `/health` rápido (liveness). Novo `/health/deep` (readiness): pinga Supabase Postgres, valida ANTHROPIC_API_KEY (HEAD api.anthropic.com), checa n8n webhook ativo.
**Critério aceite:** `/health/deep` retorna JSON `{db: ok, anthropic: ok, n8n: ok, timestamp}` e 503 se qualquer um falhar.
**Esforço:** S (1 dia).

### 5.3 Structured logging com request-id correlationável 🅼
**Motivação:** logs hoje são string interpolada (`"usuario_id=%s"`). Sem request-id propagado, é impossível correlacionar request → call n8n → log do Claude.
**Escopo:** middleware injeta `X-Request-ID` (uuid4 se ausente), `logging.getLogger().addHandler` com JSONFormatter, `n8n_service` propaga header para webhook, n8n loga em campo `request_id`.
**Critério aceite:** `grep request_id=ABC123 backend.log n8n.log` retorna trace completo.
**Esforço:** M (2-3 dias).

### 5.4 Paginação no `/contestacoes` 🅢
**Motivação:** `GET /contestacoes` retorna todas do usuário. Em produção (escritório com 500+ peças) → resposta de MB e renderização travada.
**Escopo:** query params `?limit=20&cursor=<id>`; cursor-based (não offset).
**Critério aceite:** primeira página retorna 20 + `next_cursor`; sem `next_cursor` significa fim.
**Esforço:** S.

### 5.5 Webhook de status para o frontend (SSE) 🅼🅻
**Motivação:** hoje frontend espera 9min com `AbortController`. Se n8n responde em 4min, o request HTTP fica aberto + parado por 5min sem feedback.
**Escopo:** endpoint SSE `GET /contestacoes/{id}/stream` que emite eventos `extrator_ok`, `rag_ok`, `gerador_ok`, `done`. n8n posta updates de progresso via webhook reverso.
**Critério aceite:** frontend mostra progresso "Extraindo dados (35%)" em tempo real.
**Esforço:** L (1-2 semanas — exige mudança no workflow n8n).

### 5.6 Limite de tamanho do upload no Pydantic 🅢
**Motivação:** `ContestacaoPorPeticao.arquivo_peticao_base64` aceita string arbitrária. Upload de 100MB de base64 carrega tudo em RAM antes de validar.
**Escopo:** middleware `MaxBodySizeMiddleware` (10MB hard limit) + `max_length` no `Field` do pydantic (~13MB base64 = ~10MB real).
**Critério aceite:** POST com body 15MB → 413 Payload Too Large.
**Esforço:** S.

### 5.7 Endpoint `DELETE /contestacoes/{id}` (LGPD Art. 18 VI) 🅼
**Motivação:** não há fluxo para titular deletar dados. Requisito LGPD (cf. spec 06).
**Escopo:** soft delete (`deleted_at`) → job semanal hard delete após 30 dias. Audit log.
**Critério aceite:** após soft delete, contestação some de `GET /contestacoes` mas pode ser restaurada via admin nos 30 dias.
**Esforço:** M.

---

## 6. Métricas que faltam

| Métrica | Como medir | Por que importa |
|---|---|---|
| Latência P50/P99 por endpoint | Prometheus histogram via `prometheus-fastapi-instrumentator` | SLA, regressão em PRs |
| Taxa de fallback n8n (sem Claude) | Counter `n8n_fallback_total{workflow}` | Detecta API key expirada/quota |
| Custo Anthropic por contestação | Extrair `tokens_input/output` da resposta n8n, calcular R$/contestação | Controle financeiro; viabilidade comercial |
| Confiança média do Extrator | Histogram do campo `dados_confianca` | Qualidade da extração ao longo do tempo |
| Taxa de revisão humana | Counter `revisao_humana_total / contestacao_total` | Indica se threshold 0.7 está bem calibrado |
| Hit rate do cache Supabase token | Counter `supabase_cache_hit / miss` | Validar TTL 30s e cap de 500 entradas |

---

## 7. Cobertura de testes

**Existentes (269 testes):**
- `test_routes_contestacao_peticao.py` — happy + falhas n8n + revisão humana
- `test_routes_edicao.py`, `test_routes_feedback.py`, `test_routes_suporte.py`, `test_routes_usuario.py`, `test_routes_contestacao.py`
- `test_security*.py`, `test_path_traversal.py`, `test_mime_validation.py`, `test_rate_limit.py`
- `test_docx_editor.py`, `test_diff_minuta.py`, `test_n8n_schema.py`, `test_n8n_retry.py`
- `test_ocr_fallback.py`, `test_long_context.py`, `test_load_env_file.py`

**Gaps prioritários:**
1. `embedding_service.py` — sem teste isolado (só indireto via integração). Adicionar `test_embedding_service.py` com fake model.
2. `n8n_service.py` retry com timeout — `test_n8n_retry.py` existe mas não cobre 5xx vs 4xx distinção (4xx não deve retry).
3. `_disparar_embedding` thread daemon — sem teste. Verificar que falha de DB não derruba processo.
4. `confirmar_extracao` race: contestação removida entre `get_contestacao` e `atualizar_contestacao_pos_revisao`.
5. `/baixar` quando `modelo_base_b64` é base64 corrompido (deveria cair no programático, mas é coberto?).
6. `security.py` — token cache eviction sob carga (gerar 600 tokens distintos, validar cap).

---

## 8. Priorização sugerida

**P0 (correção iminente):**
- R2 (DoS via OCR sem timeout) — risco de produção real
- R3 (thread daemon perde embedding) — degradação silenciosa
- 5.6 (limite de upload) — proteção básica

**P1 (estabilidade):**
- R1 (refactor de `database.py`)
- R6 (circuit breaker n8n)
- 5.2 (healthcheck profundo)
- 5.3 (structured logging)

**P2 (produto):**
- 5.1 (idempotency)
- 5.4 (paginação)
- 5.5 (SSE progresso)
- 5.7 (DELETE contestação)

**P3 (excelência operacional):**
- 5.x métricas Prometheus
- Refactors 4.1-4.6
