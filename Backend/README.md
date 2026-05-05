# Backend

API FastAPI do projeto de automacao de contestacao com integracao n8n e persistencia em PostgreSQL.

## Requisitos

- Python 3.10+
- PostgreSQL 14+

## Configuracao

1. Copie `.env.example` para `.env`.
2. Ajuste `N8N_WEBHOOK_URL` e `FRONTEND_ORIGINS`.
3. Se o webhook do n8n exigir auth, configure `N8N_WEBHOOK_AUTH_TOKEN`.
4. Configure `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` para validar Bearer token do frontend.
5. Configure a conexao PostgreSQL.
6. Configure opcoes de sessao (`SESSION_TTL_HOURS`, `SESSION_COOKIE_*`) quando necessario.
7. Configure SMTP do canal de suporte (`SUPPORT_SMTP_*`, `SUPPORT_EMAIL_*`).

## Variaveis do agente de IA (n8n)

O workflow n8n `AutoJuri - Webhook Contestacao Claude` usa estas variaveis no processo do n8n:

```env
ANTHROPIC_API_KEY=sua_anthropic_api_key
CLAUDE_MODEL=claude-sonnet-4-6
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_VERSION=2023-06-01
CLAUDE_MAX_TOKENS=6000
CLAUDE_TEMPERATURE=0.12
CLAUDE_TIMEOUT_MS=120000
```

Sem `ANTHROPIC_API_KEY`, o workflow entra em fallback local determinist para nao interromper o fluxo.

Opcao 1 (recomendada): `DATABASE_URL`

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/contestacao_db
```

Opcao 2: variaveis separadas (quando nao quiser URL completa)

```env
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=contestacao_db
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_SSLMODE=prefer
DATABASE_CONNECT_TIMEOUT=5
SESSION_TTL_HOURS=12
SESSION_COOKIE_NAME=contestacao_session
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_SECURE=false
SUPPORT_SMTP_HOST=smtp.seuprovedor.com
SUPPORT_SMTP_PORT=587
SUPPORT_SMTP_USER=suporte@seudominio.com
SUPPORT_SMTP_PASSWORD=sua_senha_smtp
SUPPORT_EMAIL_FROM=suporte@seudominio.com
SUPPORT_EMAIL_TO=suporte@seudominio.com
SUPPORT_EMAIL_SUBJECT_PREFIX=[JurisFlow][Suporte]
N8N_WEBHOOK_AUTH_TOKEN=
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxxxxxxxxxxxxxxxxxxx
SUPABASE_AUTH_TIMEOUT_SECONDS=8
```

## Executar localmente

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Validar conexao com PostgreSQL

Com o backend em execucao:

- `GET /health` - status geral da API
- `GET /health/db` - testa conexao real com PostgreSQL (`SELECT 1`)

## Endpoints principais

- `GET /` - status basico do backend
- `GET /health` - healthcheck
- `GET /health/db` - healthcheck da conexao PostgreSQL
- `POST /api/gerar-contestacao` - envia dados para n8n e registra no PostgreSQL
- `GET /api/contestacoes/resumo` - retorna cards e historico reais do dashboard (por usuario autenticado)
- `POST /api/usuarios/cadastro` - cria conta de usuario com validacao de email/senha
- `POST /api/usuarios/login` - autentica usuario por email/senha
- `POST /api/usuarios/logout` - invalida token de sessao no servidor
- `GET /api/usuarios/sessao` - valida sessao atual via cookie/Authorization
- `POST /api/suporte/contato` - recebe reclamacao e encaminha por e-mail para o suporte

## Seguranca e sessao

- O backend aceita sessao legada por cookie HTTPOnly/token opaco.
- O backend tambem aceita `Authorization: Bearer <jwt-do-supabase>` e valida no endpoint `auth/v1/user` do Supabase.
- O endpoint `POST /api/gerar-contestacao` exige autenticacao.
- CORS esta com `allow_credentials=True`, entao o frontend deve usar `credentials: "include"`.

## Testes

```bash
cd Backend
pip install -r requirements-dev.txt
pytest
```
