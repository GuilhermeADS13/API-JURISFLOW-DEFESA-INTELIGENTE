# JurisFlow - Automacao de Contestacoes Juridicas

Sistema web fullstack para automacao de contestacoes juridicas. O usuario preenche os dados do processo (numero CNJ, partes, fatos, pedido do autor) e o sistema gera automaticamente uma minuta de contestacao utilizando IA via workflow n8n, com suporte a Claude (Anthropic) e OpenAI como fallback.

## Funcionalidades

- **Geracao automatizada de contestacoes** com IA (Claude/OpenAI) via workflow n8n
- **Autenticacao dupla**: sistema proprio (cadastro/login com cookie HTTPOnly) + Supabase Auth
- **Upload de peca base** (PDF, DOC, DOCX) com validacao de extensao, MIME type e limite de 10MB
- **Dashboard** com historico de casos, cards de resumo (total, concluidas, em analise, pendencias)
- **Edicao ao vivo** da minuta gerada antes do envio final
- **Canal de suporte** com envio de reclamacoes por e-mail e protocolo automatico
- **Rate limiting** em todos os endpoints criticos: cadastro (5/min), login (10/min), gerar-contestacao (2/min), resumo (10/min), suporte/contato (5/min)
- **Security headers** em todas as respostas (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
- **Validacao MIME via magic bytes** no upload de arquivos (PDF, DOC, DOCX verificados no conteudo, nao so na extensao)
- **Protecao contra path traversal** com `os.path.basename()` no nome de arquivo
- **Schema validado** da resposta do n8n com Pydantic (`N8NResponse`) — campos extras ignorados
- **Sessoes com cache em memoria** e cleanup automatico de sessoes expiradas

## Arquitetura

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    Frontend      │       │    Backend       │       │      n8n        │
│  React 19 + Vite │──────▶│  FastAPI + Python │──────▶│  Workflow IA    │
│  Bootstrap 5     │  HTTP │  PostgreSQL      │  POST │  Claude/OpenAI  │
│  Supabase Auth   │◀──────│  Cookie HTTPOnly │◀──────│  Webhook        │
└─────────────────┘       └─────────────────┘       └─────────────────┘
```

## Estrutura do Projeto

```
API-DE-AUTOMA-AO-DE-CONTESTACAO/
├── Backend/
│   ├── main.py                    # Ponto de entrada FastAPI
│   ├── App/
│   │   ├── database.py            # Conexao PostgreSQL, pool, schema, CRUD
│   │   ├── security.py            # Autenticacao, sessao, cookie, Supabase Auth
│   │   ├── limiter.py             # Rate limiting (slowapi)
│   │   ├── models/
│   │   │   ├── processo.py        # Schema Pydantic do processo (validacao CNJ, MIME, path traversal)
│   │   │   ├── n8n_response.py    # Schema da resposta n8n (extra="ignore")
│   │   │   ├── usuario.py         # Schemas de cadastro/login
│   │   │   └── suporte.py         # Schema de contato/suporte
│   │   ├── routes/
│   │   │   ├── contestacao.py     # POST /api/gerar-contestacao (2/min), GET /api/contestacoes/resumo (10/min)
│   │   │   ├── usuario.py         # POST cadastro/login/logout, GET sessao
│   │   │   └── suporte.py         # POST /api/suporte/contato (5/min)
│   │   └── services/
│   │       ├── n8n_service.py     # Integracao webhook n8n (timeout 60s configuravel)
│   │       ├── auth_service.py    # Hash e verificacao de senha
│   │       └── suporte_email_service.py  # Envio de e-mail de suporte
│   ├── tests/
│   │   ├── conftest.py            # Reset do rate limiter entre testes (autouse)
│   │   ├── test_rate_limit.py     # 429 apos N requests nos endpoints protegidos
│   │   ├── test_path_traversal.py # Sanitizacao de nomes de arquivo maliciosos
│   │   ├── test_mime_validation.py# Magic bytes: EXE disfarçado de PDF rejeitado
│   │   ├── test_n8n_schema.py     # Campos extras ignorados; campos obrigatorios validados
│   │   ├── test_security_headers.py # X-Content-Type-Options, X-Frame-Options, Referrer-Policy
│   │   └── test_security_audit.py # 31 vetores: SQL injection, XSS, DoS, auth bypass, MIME spoofing
│   ├── requirements.txt           # Dependencias de producao
│   └── requirements-dev.txt       # Dependencias de desenvolvimento (pytest, httpx)
│
├── Front comp/vite-project/
│   ├── src/
│   │   ├── App.jsx                # Componente raiz (auth, envio, dashboard)
│   │   ├── config/
│   │   │   └── api.js             # URLs centralizadas da API
│   │   ├── components/
│   │   │   ├── AppNavbar.jsx      # Barra de navegacao
│   │   │   ├── AuthModal.jsx      # Modal de login/cadastro
│   │   │   ├── HeroSection.jsx    # Secao inicial
│   │   │   ├── MainPanelSection.jsx  # Formulario de contestacao
│   │   │   ├── DashboardSection.jsx  # Historico e cards
│   │   │   ├── StatsSection.jsx   # Estatisticas
│   │   │   ├── SupportSection.jsx # Formulario de suporte
│   │   │   ├── AppFooter.jsx      # Rodape
│   │   │   └── ui/StatusBadge.jsx # Badge de status
│   │   ├── utils/
│   │   │   ├── validators.js      # Validacao de e-mail, senha, CNJ
│   │   │   ├── files.js           # Validacao de arquivo, leitura base64
│   │   │   ├── storage.js         # Persistencia localStorage (rascunho/sessao)
│   │   │   ├── html.js            # Escape HTML (protecao XSS)
│   │   │   ├── cases.js           # Geracao de ID de caso
│   │   │   ├── validators.test.js # 65 testes
│   │   │   ├── files.test.js      # 23 testes
│   │   │   ├── storage.test.js    # 15 testes
│   │   │   ├── html.test.js       # 11 testes
│   │   │   └── cases.test.js      # 7 testes
│   │   ├── lib/
│   │   │   └── supabaseClient.js  # Cliente Supabase Auth
│   │   └── data/
│   │       └── mockData.js        # Dados mock para desenvolvimento
│   ├── package.json
│   └── vite.config.js             # Configuracao Vite + Vitest + coverage
│
└── docker-compose.yml             # Container n8n com Claude/OpenAI/Supabase/PostgreSQL
```

## Stack Tecnologica

### Frontend
| Tecnologia | Versao | Funcao |
|---|---|---|
| React | 19.2 | Biblioteca de UI |
| Vite | 7.3 | Build tool e dev server |
| Bootstrap 5 | 5.3 | Framework CSS |
| React Bootstrap | 2.10 | Componentes Bootstrap para React |
| Supabase JS | 2.100 | Autenticacao OAuth/social |
| Vitest | 3.2 | Framework de testes unitarios |
| @vitest/coverage-v8 | 3.2 | Cobertura de codigo |

### Backend
| Tecnologia | Versao | Funcao |
|---|---|---|
| Python | 3.12+ | Linguagem |
| FastAPI | 0.116 | Framework web |
| Uvicorn | 0.35 | Servidor ASGI |
| psycopg2 | 2.9 | Driver PostgreSQL |
| slowapi | 0.1 | Rate limiting |
| Pydantic | v2 | Validacao de schemas |

### Infraestrutura
| Tecnologia | Funcao |
|---|---|
| PostgreSQL (Supabase) | Banco de dados |
| n8n (Docker) | Orquestrador de workflow IA |
| Claude (Anthropic) | Motor de IA principal |
| OpenAI (GPT-4o) | Motor de IA fallback |

## Endpoints da API

### Contestacao
| Metodo | Endpoint | Descricao | Auth |
|---|---|---|---|
| POST | `/api/gerar-contestacao` | Envia dados para geracao via n8n | Sim |
| GET | `/api/contestacoes/resumo` | Cards e historico do dashboard | Sim |

### Usuarios
| Metodo | Endpoint | Descricao | Auth |
|---|---|---|---|
| POST | `/api/usuarios/cadastro` | Cria conta (rate limit: 5/min) | Nao |
| POST | `/api/usuarios/login` | Autentica usuario (rate limit: 10/min) | Nao |
| POST | `/api/usuarios/logout` | Encerra sessao | Nao |
| GET | `/api/usuarios/sessao` | Valida sessao ativa | Sim |

### Suporte
| Metodo | Endpoint | Descricao | Auth |
|---|---|---|---|
| POST | `/api/suporte/contato` | Envia reclamacao por e-mail | Nao |

### Healthcheck
| Metodo | Endpoint | Descricao |
|---|---|---|
| GET | `/` | Status do backend |
| GET | `/health` | Healthcheck basico |
| GET | `/health/db` | Healthcheck do banco PostgreSQL |

## Como Executar

### Frontend

```bash
cd "Front comp/vite-project"
npm install
npm run dev
```

Acesse em `http://localhost:5173`

### Backend

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### n8n (Docker)

```bash
docker-compose up -d
```

Acesse o painel em `http://localhost:5678`

## Variaveis de Ambiente

### Backend (`Backend/.env`)
| Variavel | Descricao |
|---|---|
| `FRONTEND_ORIGINS` | Origens CORS permitidas (default: localhost:5173) |
| `N8N_WEBHOOK_URL` | URL do webhook n8n |
| `N8N_TIMEOUT_SECONDS` | Timeout da chamada ao n8n em segundos (default: 60) |
| `DATABASE_URL` | URL completa do PostgreSQL |
| `DATABASE_HOST` | Host do banco (alternativa ao DATABASE_URL) |
| `DATABASE_PORT` | Porta do banco (default: 5432) |
| `DATABASE_NAME` | Nome do banco (default: contestacao_db) |
| `DATABASE_USER` | Usuario do banco |
| `DATABASE_PASSWORD` | Senha do banco (obrigatoria) |
| `SESSION_TTL_HOURS` | Duracao da sessao em horas (default: 12) |
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_PUBLISHABLE_KEY` | Chave publica do Supabase |

### Frontend (`Front comp/vite-project/.env`)
| Variavel | Descricao |
|---|---|
| `VITE_API_BASE_URL` | URL base da API (default: http://localhost:8000/api) |
| `VITE_SUPABASE_URL` | URL do projeto Supabase |
| `VITE_SUPABASE_ANON_KEY` | Chave anonima do Supabase |

## Testes

### Frontend (Vitest)
```bash
cd "Front comp/vite-project"
npm test                # executa 121 testes
npm run test:coverage   # executa com relatorio de cobertura
```

**Cobertura atual: 94,69% statements | 100% functions**

| Arquivo | Statements | Branches | Functions |
|---|---|---|---|
| validators.js | 100% | 100% | 100% |
| cases.js | 100% | 100% | 100% |
| html.js | 100% | 100% | 100% |
| files.js | 83% | 86% | 100% |
| storage.js | 97% | 80% | 100% |

### Backend (pytest)
```bash
cd Backend
pip install -r requirements-dev.txt
pytest                              # executa 126 testes
pytest tests/test_security_audit.py -v  # varredura de vulnerabilidades
```

## Seguranca

- Sessao por **cookie HTTPOnly** (nao acessivel via JavaScript)
- **Rate limiting** em todos os endpoints criticos (2-10 req/min conforme risco)
- Validacao de **MIME via magic bytes** — PDF (`%PDF`), DOC (`\xD0\xCF\x11\xE0`), DOCX (`PK\x03\x04`) verificados no conteudo do arquivo, nao apenas na extensao
- **Protecao contra path traversal** — `os.path.basename()` sanitiza nomes como `../../etc/passwd.pdf` → `passwd.pdf`
- **Security headers** em todas as respostas: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin`
- **Schema validado** da resposta do n8n — `N8NResponse(BaseModel)` descarta campos extras e valida tipos
- **Escape de HTML** para prevencao de XSS no frontend
- Senhas com hash seguro (nunca armazenadas em texto plano)
- `persistSession` **filtra tokens** — apenas id, nome e email sao salvos no localStorage
- CORS configuravel por variavel de ambiente
- **Varredura automatizada** de vulnerabilidades — 31 vetores de ataque cobertos em `test_security_audit.py` (SQL injection, XSS, path traversal, DoS, auth bypass, MIME spoofing)
