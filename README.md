# JurisFlow AI — Automação de Contestações Jurídicas

Sistema web fullstack para geração automatizada de contestações trabalhistas/cíveis. O advogado faz upload da petição inicial em PDF/DOCX, o sistema extrai os dados via IA, consulta defesas anteriores do escritório no RAG semântico, gera uma minuta estruturada (preliminares A-G, mérito ponto-a-ponto, fundamentos, pedidos) e entrega o `.docx` ou `.pdf` final pronto pra protocolar — com o mesmo timbre, fonte e estilo do escritório.



---

## Sumário

- [Funcionalidades](#funcionalidades)
- [Arquitetura](#arquitetura)
- [Pipeline de geração](#pipeline-de-geração)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Stack tecnológica](#stack-tecnológica)
- [Endpoints da API](#endpoints-da-api)
- [Como executar](#como-executar)
- [Migrations do banco](#migrations-do-banco)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Testes](#testes)
- [Segurança](#segurança)

---

## Funcionalidades

- **Upload de petição inicial** (PDF ou DOCX, até 20MB). Sistema extrai dados estruturados via Claude Sonnet 4.6.
- **OCR fallback** automático pra PDFs digitalizados (Tesseract + Poppler) — Súmula 338 TST não fica de fora.
- **RAG semântico em defesas anteriores** do próprio escritório (pgvector + sentence-transformers MiniLM-L12, 384 dims). A IA copia tese central, preliminares e estratégia dos exemplares aprovados.
- **Geração da minuta** com Claude Sonnet 4.6 — 7 preliminares trabalhistas obrigatórias (A–G), mérito subseções (II.A, II.B…), litigância de má-fé, danos morais, autenticidade, pedidos.
- **Self-correction de citações** (Claude Haiku 4.5) — checa cada Súmula/artigo/jurisprudência citado contra a base legal vigente e marca incertos.
- **Detecção de lacunas factuais** — quando a petição não traz fato necessário (data, salário, jornada), a IA registra em `riscos[]` em vez de inventar.
- **Builder DOCX adaptativo** — preserva fonte, espaçamento e cabeçalho do modelo base do escritório. Default Arial 12pt + line-spacing 1.15 (alinhado ao padrão Word "Normal").
- **Conversão para PDF server-side** via LibreOffice headless (paginação idêntica entre Word e LibreOffice).
- **Edição cirúrgica de modelos** — substituição de campos (autor, réu, valor da causa) em DOCX preservando 100% da formatação.
- **Dashboard com histórico** — cards de status, filtros, ações por peça (Baixar DOCX, Baixar PDF, Excluir).
- **Revisão Humana (HiL)** — quando a confiança da extração fica abaixo de 0.7, o sistema abre modal pro advogado corrigir antes de gerar a minuta.
- **Feedback loop** — advogado marca peça como útil/não-útil; coordenação curadora promove a `contestacoes_exemplares` (vira referência pro RAG).
- **Cadastro e login** via Supabase Auth (e-mail/senha + OAuth social).
- **Canal de suporte** com protocolo automático.

---

## Arquitetura

```text
┌──────────────────┐      ┌────────────────────┐      ┌──────────────────────┐
│    Frontend       │      │     Backend         │      │      n8n (Docker)      │
│  React 19 + Vite  │─────▶│  FastAPI + Python   │─────▶│  3 workflows ativos    │
│  Bootstrap 5      │ HTTP │  python-docx        │ POST │   ├ contestacao-claude  │
│  Supabase Auth    │◀─────│  pdf2image+OCR      │ JSON │   ├ contestar-peticao   │
│                   │      │  LibreOffice→PDF    │      │   └ editar-contestacao │
└──────────────────┘      └────────────────────┘      └──────────┬─────────────┘
                                    │                            │
                                    │                ┌───────────▼─────────────┐
                                    │                │   Claude API (Anthropic) │
                                    │                │   - sonnet-4-6 (extr+ger)│
                                    │                │   - haiku-4-5 (verif)    │
                                    │                └──────────────────────────┘
                                    │
                          ┌─────────▼──────────┐
                          │  Supabase Postgres │
                          │  + pgvector 0.8    │
                          │  + RLS policies    │
                          └────────────────────┘
```

---

## Pipeline de geração

```text
1. Upload PDF/DOCX ──┐
                     ▼
2. Backend extrai texto (pypdf + pdf2image+Tesseract fallback)
                     │
                     ▼
3. POST /webhook/contestar-por-peticao ──▶ n8n
                                            │
                     ┌──────────────────────┘
                     ▼
4. Claude Extrator (Sonnet 4.6, max_tokens 8000) → dados_extraidos + confianca
                     │
                     ▼ se confianca >= 0.7
5. RAG no Supabase → busca top-3 defesas similares (cosine via pgvector)
                     │
                     ▼
6. Claude Gerador (Sonnet 4.6, max_tokens 16000) → minuta JSON
   - SYSTEM_PROMPT com 100+ regras (preliminares A-G, hierarquia FORMA/TESE, lacunas factuais)
   - Cache ephemeral do SYSTEM + modelo_base (-3k tokens em calls subsequentes)
   - Retry com backoff em 429/529/500 (socket abort)
   - JSON repair heurístico se output tiver aspas duplas internas
                     │
                     ▼
7. Self-Correction (Haiku 4.5) → cita_incertas[] + cita_verificadas[]
                     │
                     ▼
8. Backend monta DOCX (python-docx + line_spacing 1.15 + font 12pt + WD_LINE_SPACING.MULTIPLE)
                     │
                     ▼
9. Conversão DOCX→PDF (libreoffice --headless --convert-to pdf, UserInstallation isolado)
                     │
                     ▼
10. Resposta: {arquivo_editado_base64, nome.pdf, riscos[], citacoes_incertas[]}
```

Tempo médio: **~5–6 min** end-to-end. Custo médio: **$0,25** por peça (5–7 mil tokens output Sonnet + 11k cache create + Haiku verify).

---

## Estrutura do projeto

```text
API-CONTESTACAO/
├── Backend/
│   ├── main.py                              # FastAPI app + middlewares
│   ├── requirements.txt                     # 30+ pacotes pinados
│   ├── Dockerfile                           # multi-stage build com LibreOffice + Tesseract
│   ├── App/
│   │   ├── database.py                      # CRUD PostgreSQL, schema bootstrap, pool
│   │   ├── security.py                      # Supabase Auth + cookie HTTPOnly
│   │   ├── limiter.py                       # slowapi rate-limiting global
│   │   ├── models/
│   │   │   ├── processo.py                  # Pydantic + validador CNJ
│   │   │   ├── contestacao_por_peticao.py   # schema do fluxo via petição
│   │   │   ├── edicao.py                    # schema da edição cirúrgica
│   │   │   ├── exemplar.py                  # schema admin (curadoria)
│   │   │   ├── feedback.py                  # schema feedback útil/não-útil
│   │   │   ├── n8n_response.py              # validação resposta n8n
│   │   │   ├── suporte.py                   # schema canal suporte
│   │   │   └── usuario.py                   # schema cadastro/login
│   │   ├── routes/
│   │   │   ├── contestacao.py               # POST /gerar-contestacao + GET /resumo
│   │   │   ├── contestacao_peticao.py       # POST /contestar-por-peticao + baixar + delete + minuta
│   │   │   ├── edicao.py                    # POST /editar-contestacao (edição cirúrgica DOCX)
│   │   │   ├── feedback.py                  # POST /feedback + /admin/exemplares
│   │   │   ├── rag.py                       # POST /rag/defesas-similares
│   │   │   ├── usuario.py                   # cadastro/login/logout/sessao
│   │   │   └── suporte.py                   # POST /suporte/contato
│   │   └── services/
│   │       ├── n8n_service.py               # cliente HTTP n8n + retry + Bearer
│   │       ├── contestacao_docx_builder.py  # python-docx renderer adaptativo
│   │       ├── docx_style_defaults.py       # SOURCE OF TRUTH: font 12pt + line 1.15
│   │       ├── docx_editor.py               # substituição cirúrgica preservando runs
│   │       ├── diff_minuta.py               # diff entre minuta IA e edição humana
│   │       ├── embedding_service.py         # sentence-transformers MiniLM-L12 (384d)
│   │       ├── pdf_converter.py             # libreoffice --headless --convert-to pdf
│   │       ├── peticao_extractor.py         # pypdf + Tesseract fallback OCR
│   │       ├── auth_service.py              # bcrypt password hash
│   │       └── suporte_email_service.py     # SMTP envio canal suporte
│   ├── migrations/                          # SQL versionado (auditoria DB)
│   │   ├── README.md                        # como reaplicar via MCP/CLI
│   │   └── 2026060416*.sql                  # 4 migrations: RLS + index + revoke
│   └── tests/                               # 30 arquivos pytest (12k+ LOC, 269 testes)
│
├── Front end/vite-project/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx                          # raiz + autenticação + roteamento
│       ├── styles.css                       # tema dark unificado (--uniform-*)
│       ├── components/
│       │   ├── AppNavbar.jsx / AppFooter.jsx
│       │   ├── AuthModal.jsx                # login/cadastro/recuperar
│       │   ├── HeroSection.jsx              # landing
│       │   ├── StatsSection.jsx             # cards de métricas
│       │   ├── MainPanelSection.jsx         # formulário envio (manual + petição)
│       │   ├── DashboardSection.jsx         # histórico + Baixar + Excluir
│       │   ├── SupportSection.jsx           # canal suporte
│       │   ├── RevisaoHumanaModal.jsx       # HiL — correção da extração
│       │   └── ui/StatusBadge.jsx
│       ├── config/api.js                    # URLs centralizadas
│       ├── data/mockData.js                 # ramos jurídicos + subtipos
│       ├── lib/supabaseClient.js
│       └── utils/                           # validators, files, storage, html, cases
│
├── docs/
│   ├── n8n_workflow_contestacao_claude.json       # fluxo manual
│   ├── n8n_workflow_contestar_por_peticao.json    # fluxo principal (RAG + legislação)
│   ├── n8n_workflow_editar_contestacao.json       # edição cirúrgica
│   ├── AGENTE_IA_AUTOJURI.md                # spec do agente
│   ├── OPERACOES_N8N.md                     # admin REST API n8n
│   ├── CONTEXTO_PARA_CLAUDE.md              # contexto pro Claude Code
│   ├── contestacoes_exemplares_seed.sql     # seed inicial do RAG
│   ├── specs/                               # specs vivos por componente
│   ├── screenshots/                         # capturas de tela do produto
│   ├── historico/                           # entregas acadêmicas + relatórios antigos
│   │   ├── ENTREGA_FINAL.md / .pdf
│   │   ├── EVIDENCIAS_ETAPA5.md / .pdf
│   │   ├── RELATORIO_METRICAS.md / .pdf
│   │   └── ... (CHANGELOG_PR9_2, REVISAO_2026-04-29, RISCOS_E_PRIORIDADES, JurisFlow_*)
│   └── _dev/                                # scripts dev ativos (patches workflow, reimport, smoke)
│       └── _archived/                       # scripts one-shot já rodados (preservados em git)
│
├── docker-compose.yml                       # backend + n8n + volumes nomeados
├── .env.example                             # template raiz (Anthropic+Supabase+n8n)
├── .gitignore                               # protege .env, .mcp.json, .credentials
└── scripts/                                 # helpers shell
```

---

## Stack tecnológica

### Frontend

| Tecnologia | Versão | Função |
|---|---|---|
| React | 19.2 | UI |
| Vite | 7.3 | Build + HMR |
| Bootstrap 5 + React-Bootstrap | 5.3 / 2.10 | Design system |
| Supabase JS | 2.100 | Auth (e-mail + OAuth) |
| react-imask | 7.6 | Máscara CNJ |
| Vitest + @vitest/coverage-v8 | 3.2 | Testes |

### Backend

| Tecnologia | Versão | Função |
|---|---|---|
| Python | 3.12 | Linguagem |
| FastAPI | 0.116 | Framework HTTP |
| Uvicorn (standard) | 0.35 | ASGI server |
| Pydantic | 2.13 | Schemas + validação |
| psycopg2-binary | 2.9 | Driver PostgreSQL |
| slowapi | 0.1 | Rate limiting |
| python-docx | 1.1 | Geração DOCX |
| pypdf | 4.3 | Extração PDF |
| pytesseract + pdf2image + Pillow | 0.3 / 1.17 / 12.2 | OCR fallback |
| sentence-transformers | ≥3 | Embeddings MiniLM-L12 (384d) |

### Infraestrutura

| Componente | Função |
|---|---|
| Supabase PostgreSQL + pgvector 0.8 | DB + vector search |
| n8n 2.17 (Docker) | Orquestrador (3 workflows ativos) |
| LibreOffice 25.2 (no container backend) | DOCX → PDF |
| Claude API (Anthropic) | Sonnet 4.6 (extr+ger) + Haiku 4.5 (verif) |
| Tesseract OCR + Poppler | PDF digitalizado |

---

## Endpoints da API

Todas rotas sob `/api`. Rate limits via `slowapi` (IP-based).

### Contestação — fluxo manual (`Backend/App/routes/contestacao.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/gerar-contestacao` | Gera contestação a partir do formulário manual (dados já estruturados) | `RATE_LIMIT_CONTESTACAO` (2/min default) | ✅ |
| GET | `/contestacoes/resumo` | Cards + histórico do dashboard | `RATE_LIMIT_DASHBOARD` (30/min default) | ✅ |
| GET | `/contestacoes/{id}` | Detalhes de uma contestação (IDOR-safe via usuario_id) | `RATE_LIMIT_DASHBOARD` | ✅ |

### Contestação — fluxo por petição (`Backend/App/routes/contestacao_peticao.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/contestar-por-peticao` | Upload de PDF/DOCX + extração + RAG + geração | 5/min, 30/hour | ✅ |
| POST | `/contestacoes/{id}/confirmar-extracao` | HiL — advogado corrige extração e re-gera | 10/min | ✅ |
| GET | `/contestacoes/{id}/baixar?formato=docx\|pdf` | Download regenerado (DOCX nativo ou PDF via LibreOffice) | 30/min | ✅ |
| PATCH | `/contestacoes/{id}/minuta` | Salva edição manual da minuta | 30/min | ✅ |
| DELETE | `/contestacoes/{id}` | Exclui peça (IDOR-safe) | 20/min | ✅ |

### Edição cirúrgica (`Backend/App/routes/edicao.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/editar-contestacao` | Substituição de campos em DOCX preservando formatação | 5/min | ✅ |

### Feedback + curadoria (`Backend/App/routes/feedback.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/contestacoes/{id}/feedback` | Marca peça como útil/não-útil + comentário | 20/min | ✅ |
| POST | `/admin/exemplares` | Promove contestação a exemplar curado (RAG) | 10/min | ✅ admin only |
| GET | `/admin/exemplares` | Lista exemplares curados | 20/min | ✅ admin only |

### RAG (`Backend/App/routes/rag.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/rag/defesas-similares` | Busca semântica top-K em `contestacoes_exemplares` | 30/min | ✅ |

### Usuários (`Backend/App/routes/usuario.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/usuarios/cadastro` | Cria conta | 5/min | ❌ |
| POST | `/usuarios/login` | Autentica | 10/min | ❌ |
| POST | `/usuarios/logout` | Encerra sessão | — | ❌ |
| GET | `/usuarios/sessao` | Valida sessão ativa | — | ✅ |

### Suporte (`Backend/App/routes/suporte.py`)
| Método | Endpoint | Descrição | Rate limit | Auth |
|---|---|---|---|---|
| POST | `/suporte/contato` | Abre chamado com protocolo | 5/min | ❌ |

### Healthcheck (`Backend/main.py`)
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Backend up |
| GET | `/health/db` | DB conectado |

---

## Como executar

### Pré-requisitos

| Ferramenta | Versão mínima | Para que serve |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop) | 4.x | Backend + n8n em containers (rota recomendada) |
| [Node.js](https://nodejs.org/) | 20 LTS | Frontend Vite |
| [Python](https://www.python.org/downloads/) | 3.12+ | Backend isolado (sem Docker) |
| [Git](https://git-scm.com/) | 2.x | Clonar |

Verifique:
```bash
docker --version && node --version && python --version && git --version
```

### 1. Arquivos de ambiente

Copie e preencha:
```bash
cp .env.example .env                                   # raiz: Anthropic + Supabase + n8n
cp Backend/.env.example Backend/.env                   # backend (caso rode fora do Docker)
cp "Front end/vite-project/.env.example" "Front end/vite-project/.env"
```

### 2. Subir backend + n8n (Docker)

```bash
docker compose build backend     # IMPORTANTE: sempre rebuild depois de mexer em Backend/
docker compose up -d
```

- Backend: `http://localhost:8000`
- n8n: `http://localhost:5678`
- Volumes preservados: `autojuri_n8n_data` (workflows + credentials), `autojuri_hf_cache` (modelo MiniLM, 118MB)

Pra encerrar (sem perder dados):
```bash
docker compose down              # NUNCA usar -v: apaga volumes
```

### 3. Subir frontend (Vite)

```bash
cd "Front end/vite-project"
npm install
npm run dev                      # http://localhost:5173
```

### 4. Backend isolado (sem Docker — opcional)

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Sem container, **PDF não funciona** (depende do LibreOffice instalado no Dockerfile). Pra testar PDF localmente, instale LibreOffice no host.

### 5. Health-check

```bash
curl http://localhost:8000/health        # backend
curl http://localhost:8000/health/db     # backend + DB
curl http://localhost:5678/healthz       # n8n
```

---

## Migrations do banco

DDL versionado em `Backend/migrations/`:

| Versão | Nome | Categoria |
|---|---|---|
| `20260604164243` | `revoke_rls_auto_enable_from_public_roles` | 🔴 segurança |
| `20260604164246` | `add_index_usuarios_sessoes_usuario_id` | 🟠 performance |
| `20260604164248` | `rls_policies_baseline_5_tables` | 🟠 segurança / docs |
| `20260604164347` | `deny_public_access_to_configuracoes` | 🟠 segurança / docs |

Detalhes em [`Backend/migrations/README.md`](Backend/migrations/README.md). Source of truth é a tabela `supabase_migrations.schema_migrations` no banco — `apply_migration` (via MCP) registra automaticamente.

---

## Variáveis de ambiente

Veja [`.env.example`](.env.example) pra lista completa. Categorias:

### Claude / Anthropic
| Variável | Descrição |
|---|---|
| `ANTHROPIC_API_KEY` | Chave da API Anthropic |
| `CLAUDE_MODEL` | Modelo principal do gerador (default `claude-sonnet-4-6`) |
| `CLAUDE_EXTRACAO_MODEL` | Modelo do extrator (default `claude-sonnet-4-6`) |
| `CLAUDE_VERIFICACAO_MODEL` | Modelo do self-correction (default `claude-haiku-4-5`) |

### Supabase
| Variável | Descrição |
|---|---|
| `SUPABASE_URL` | URL do projeto |
| `SUPABASE_PUBLISHABLE_KEY` | Chave pública (frontend) |
| `SUPABASE_ANON_KEY` | JWT anon |
| `SUPABASE_SERVICE_ROLE_KEY` | JWT service_role (backend) |
| `DATABASE_*` | host/port/user/password/sslmode do pooler PostgreSQL |

### n8n
| Variável | Descrição |
|---|---|
| `N8N_WEBHOOK_URL` | Webhook fluxo manual |
| `N8N_WEBHOOK_PETICAO` | Webhook fluxo por petição |
| `N8N_EDICAO_WEBHOOK_URL` | Webhook edição cirúrgica |
| `N8N_TIMEOUT_SECONDS` | Timeout backend → n8n (default 600s pra peça longa) |
| `N8N_WEBHOOK_AUTH_TOKEN` | Bearer opcional pra autenticar chamadas |
| `N8N_API_KEY` | Public API key (em `Backend/.env`) pra admin via REST |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `true` em prod, `false` em dev (Code nodes leem `process.env`) |

### Backend
| Variável | Descrição |
|---|---|
| `FRONTEND_ORIGINS` | Origens CORS (default `localhost:5173`) |
| `SESSION_COOKIE_SECURE` / `SESSION_COOKIE_SAMESITE` | Cookie HTTPOnly de sessão |
| `SESSION_TTL_HOURS` | Duração sessão (default 12h) |
| `LOG_LEVEL` | DEBUG / INFO / WARNING |

### Feedback loop + curadoria
| Variável | Descrição |
|---|---|
| `ADMIN_EMAILS` | E-mails com acesso ao `/admin/exemplares` |
| `BACKEND_ADMIN_TOKEN` | Bearer pra n8n chamar admin endpoints |

### OCR
| Variável | Descrição |
|---|---|
| `OCR_ENABLED` | `true` ativa fallback Tesseract |
| `OCR_MAX_PAGES` | Cap de páginas (default 15) |
| `OCR_DPI` | DPI conversão PDF → imagem (300 recomendado) |
| `OCR_LANG` | Idioma Tesseract (default `por`) |

---

## Testes

### Frontend (Vitest)
```bash
cd "Front end/vite-project"
npm test                          # 121 testes
npm run test:coverage             # relatório de cobertura
```

**Cobertura: 94,69 % statements | 100 % functions**

### Backend (pytest)
```bash
cd Backend
pip install -r requirements-dev.txt
pytest -v                                          # ~269 testes
pytest tests/test_security_audit.py -v             # 31 vetores de ataque
pytest tests/test_routes_contestacao_peticao.py -v # rotas do fluxo principal
```

Testes principais:

| Arquivo | Cobre |
|---|---|
| `test_security_audit.py` | SQL injection, XSS, path traversal, DoS, auth bypass, MIME spoofing |
| `test_path_traversal.py` | Sanitização `../etc/passwd.pdf` → `passwd.pdf` |
| `test_mime_validation.py` | Magic bytes: EXE disfarçado de PDF é rejeitado |
| `test_rate_limit.py` | 429 após N requests |
| `test_n8n_retry.py` | Retry exponencial com 429/529/500 |
| `test_n8n_schema.py` | `extra="ignore"` no Pydantic resposta |
| `test_rag_semantico.py` | pgvector cosine + threshold + fallback TF-IDF |
| `test_docx_editor.py` | Substituição cirúrgica preserva runs |
| `test_routes_contestacao_peticao.py` | Fluxo completo upload → extração → geração |
| `test_security_headers.py` | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, etc. |
| `test_ocr_fallback.py` | PDF digitalizado vai pro Tesseract |

---

## Segurança

- **Sessão por cookie HTTPOnly** (não acessível via JavaScript), `SameSite=Lax`, `Secure` em produção.
- **Rate limiting** em todos os endpoints críticos (slowapi por IP, configurável por env).
- **Validação MIME via magic bytes** (`pypdf` confirma `%PDF`, `python-docx` valida ZIP central directory). Não confia em extensão nem `Content-Type`.
- **Path traversal**: `os.path.basename()` sanitiza nomes maliciosos.
- **Security headers** em todas respostas (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy).
- **CORS configurável** via `FRONTEND_ORIGINS` — `allow_methods` lista explícita (GET/POST/PATCH/DELETE/OPTIONS).
- **Schema validado** da resposta n8n via Pydantic (descarta campos extras, força tipos).
- **Escape HTML** no frontend (`utils/html.js`).
- **Senhas hasheadas** com bcrypt — nunca em texto plano. Supabase Auth gerencia.
- **`persistSession` filtra tokens** — só `id`, `nome`, `email` vão pro localStorage.
- **RLS policies** em todas as 5 tabelas (`contestacoes`, `usuarios`, `usuarios_sessoes`, `contestacoes_exemplares`, `configuracoes`). Defesa em profundidade.
- **`rls_auto_enable()`** com `REVOKE EXECUTE` de `anon`/`authenticated` (era vetor de privilege escalation).
- **MCP config (`.mcp.json`, `.vscode/mcp.json`)** no `.gitignore` — PATs do Supabase não vazam.
- **31 vetores automatizados** em `test_security_audit.py` rodam no CI a cada PR.

---

## Operações

### Helpers de dev
- `/ligarserver` (skill Claude Code) — Docker + rebuild backend + Vite em background.
- `/desligarserver` — Vite kill + `docker compose down` preservando volumes.
- `/testar-servers` — health-check completo (12 checks: Docker, containers, portas, REST APIs, Supabase, Anthropic, MCP).

### Administrar n8n via REST
```powershell
$apiKey = ((Get-Content "Backend\.env" | Select-String "^N8N_API_KEY=").ToString() -replace "^N8N_API_KEY=", "").Trim()
$headers = @{ "X-N8N-API-KEY" = $apiKey }
Invoke-RestMethod -Uri "http://localhost:5678/api/v1/workflows" -Headers $headers
```

### Re-importar workflow após edição manual
```bash
docker exec -u node autojuri_n8n n8n import:workflow --input=/data/workflows/<nome>.json
# import sempre desativa; reativar via REST:
Invoke-RestMethod -Uri "http://localhost:5678/api/v1/workflows/<WF_ID>/activate" -Method POST -Headers $headers
```

### Backup do n8n
```bash
docker run --rm -v autojuri_n8n_data:/data -v $(pwd):/backup \
  busybox tar czf /backup/n8n_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
```

---

## Licença

Projeto Integrador — uso acadêmico/educacional. Para uso comercial, contatar o autor.
