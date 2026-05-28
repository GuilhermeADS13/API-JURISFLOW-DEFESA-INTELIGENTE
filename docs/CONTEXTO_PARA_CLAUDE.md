# 📋 Contexto AutoJuri — Guia para Claude

**Data:** 28 de maio de 2026  
**Projeto:** AutoJuri / JurisFlow — Sistema de Automação de Contestações Jurídicas  
**Status:** ✅ Etapa 5 Completa + PR9.2 Implementado  
**Versão:** 1.0

---

## 📖 Índice

1. [Arquivos Essenciais](#arquivos-essenciais)
2. [Contexto do Projeto](#contexto-do-projeto)
3. [Arquitetura Técnica](#arquitetura-técnica)
4. [Próximos Passos Recomendados](#próximos-passos-recomendados)
5. [Referência Rápida de Comandos](#referência-rápida-de-comandos)

---

## 📂 Arquivos Essenciais

### 🎯 **Leitura Prioritária (SEMPRE)**

| Arquivo | Propósito | Por quê |
|---------|-----------|--------|
| [ENTREGA_FINAL.md](./docs/ENTREGA_FINAL.md) | Visão completa do sistema + métricas | Escopo total, testes, cobertura |
| [AGENTE_IA_AUTOJURI.md](./docs/AGENTE_IA_AUTOJURI.md) | Motor Claude + limitações | Qualidade por área, jurisprudência |
| [PLANO_IMPLEMENTACAO_2026-04-29.md](./docs/PLANO_IMPLEMENTACAO_2026-04-29.md) | Roadmap Fase 1 e 2 | O que foi entregue vs pendente |
| [OPERACOES_N8N.md](./docs/OPERACOES_N8N.md) | Backup, segurança, deployment | Produção ready checklist |

### 📊 **Leitura por Contexto**

#### Se trabalhando com **n8n/Workflows**
1. `docs/n8n_workflow_contestacao_claude.json` — Fluxo principal
2. `Backend/App/services/n8n_service.py` — Integração backend
3. `docs/OPERACOES_N8N.md` — Segurança e backup

#### Se trabalhando com **Backend/FastAPI**
1. `Backend/main.py` — Configuração aplicação
2. `Backend/App/database.py` — Query builders
3. `Backend/App/routes/` — Endpoints REST
4. `Backend/App/models/` — Pydantic schemas

#### Se trabalhando com **Frontend**
1. `Front end/vite-project/package.json` — Dependências
2. `Front end/vite-project/src/` — Componentes React 19
3. `.env.example` — Variáveis necessárias

#### Se trabalhando com **Testes/CI-CD**
1. `Backend/tests/` — Suite completa (269 passed)
2. `.github/workflows/` — Pipelines GitHub Actions
3. `Backend/pytest.ini` — Configuração testes

---

## 🎓 Contexto do Projeto

### Objetivo
Automatizar a geração de contestações jurídicas trabalhistas a partir de petições iniciais em PDF/DOCX, usando:
- **Claude Sonnet 4.6** (Anthropic) — Motor de IA
- **n8n 2.17.5** (Docker) — Orquestração de workflows
- **PostgreSQL + pgvector** (Supabase) — RAG semântico

### Stack Técnica

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND (React 19 + Vite + Bootstrap)                 │
│  - Upload PDF/DOCX                                      │
│  - Edição assistida de minuta                           │
│  - Dashboard com paginação/filtros                      │
│  - Autenticação Supabase                                │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────┐
│  BACKEND (FastAPI + Python 3.14)                        │
│  - REST API (124 endpoints testados)                    │
│  - Rate limiting (30 req/min em rotas pesadas)          │
│  - Validação MIME + sanitização path-traversal          │
│  - RAG semântico (sentence-transformers)                │
│  - Fallback OCR (Tesseract para PDFs digitalizados)     │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP Docker
┌──────────────────────▼──────────────────────────────────┐
│  ORQUESTRAÇÃO (n8n 2.17.5 com Code Nodes)               │
│  - Validação de entrada                                 │
│  - Busca de defesas anteriores (Supabase)               │
│  - Chamada Claude com retry + prompt-caching            │
│  - Geração DOCX editável (base64)                       │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  DADOS (PostgreSQL + pgvector no Supabase)              │
│  - Tabelas: usuarios, contestacoes, exemplares          │
│  - Embeddings: 384-dim (multilingual MiniLM-L12-v2)     │
│  - TF-IDF + feedback scoring (Fase 2)                   │
└─────────────────────────────────────────────────────────┘
```

### Regras de Negócio Críticas

| Regra | Implementação | Motivação |
|-------|---------------|-----------|
| Confiança HiL < 0.70 | `routes/contestacao_peticao.py` | Evitar minuta baixa qualidade |
| Senha forte | `models/usuario.py::senha_forte` | OWASP — 600k PBKDF2 (roadmap) |
| Validação MIME | `models/processo.py:97-101` | Defesa contra upload disfarçado |
| Rate limit 30/min | `limiter.py` + decorators | Proteção contra abuso |
| Retry exponencial | `n8n_service.py` + workflow n8n | Robustez a falhas transitórias |

---

## 🏗️ Arquitetura Técnica

### Fluxos Principais

#### 1️⃣ **Contestação Clássica** (`/api/contestacoes/gerar-contestacao`)
```
Formulário advogado
    ↓
Backend valida campos
    ↓
Busca defesas similares (Supabase pgvector)
    ↓
Chama workflow n8n "contestacao-claude"
    ↓
Claude gera minuta com retry (3×)
    ↓
Fallback local se Claude falhar
    ↓
Retorna minuta + arquivo_editado_base64
    ↓
Frontend exibe, advogado revisa e exporta DOCX
```

#### 2️⃣ **Contestação por Petição** (`/api/contestacoes/contestacao-por-peticao`)
```
Upload PDF/DOCX (validação MIME + tamanho max 10MB)
    ↓
Extração de texto (pypdf → fallback OCR Tesseract)
    ↓
Claude Sonnet extrai: autor, réu, fatos, pedidos
    ↓
RAG semântico busca defesas anteriores
    ↓
Claude gera minuta completa
    ↓
Human-in-the-Loop: se confiança < 0.70 → revisão obrigatória
    ↓
Salva em contestacoes + gera DOCX editável
```

#### 3️⃣ **Edição Cirúrgica DOCX** (Fase 1)
```
Minuta gerada em memória (não .docx físico)
    ↓
Advogado edita campos live no frontend
    ↓
POST /api/contestacoes/{id}/editar-contestacao
    ↓
Workflow n8n "editar-contestacao" ativa
    ↓
Substitui: nome, número processo, valor causa
    ↓
Workflow fallback: mantém estilos + formatação
    ↓
Retorna .docx editado em base64
```

### Camada de Dados

**PostgreSQL (Supabase Transaction Pooler)**
```sql
-- Contestações geradas
CREATE TABLE contestacoes (
  id SERIAL PRIMARY KEY,
  numero_processo VARCHAR(40),
  usuario_id BIGINT REFERENCES usuarios,
  status ENUM('processando', 'ok', 'revisao_humana', 'erro'),
  n8n_resposta JSONB,                -- Resposta completa do workflow
  arquivo_editado_base64 TEXT,       -- DOCX em base64
  feedback_util BOOLEAN,              -- Fase 2: feedback do advogado
  criado_em TIMESTAMP DEFAULT NOW()
);

-- Exemplares para curadoria (few-shot no prompt)
CREATE TABLE contestacoes_exemplares (
  id SERIAL PRIMARY KEY,
  tipo_acao VARCHAR(100),
  tese_central TEXT,
  fundamentos TEXT,
  revisor_email VARCHAR(255),
  criado_em TIMESTAMP
);

-- Embeddings semânticos
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE contestacoes ADD COLUMN embedding vector(384);
CREATE INDEX ON contestacoes USING ivfflat (embedding vector_cosine_ops);
```

---

## 🚀 Próximos Passos Recomendados

### ✅ Implementados (Etapa 5)

| Item | Status | Link |
|------|--------|------|
| Backend FastAPI | ✅ 269 testes, 74% cobertura | [Backend/main.py](../Backend/main.py) |
| Frontend React 19 | ✅ 84% statements, 91% branches | [Front end/vite-project](../Front%20end/vite-project) |
| Workflows n8n | ✅ 3 fluxos completos | [docs/n8n_workflow_*.json](./n8n_workflow_contestacao_claude.json) |
| Segurança (PR9) | ✅ N8N_BLOCK_ENV_ACCESS=true | [OPERACOES_N8N.md](./OPERACOES_N8N.md) |
| Backup n8n | ✅ Script automático criado | [scripts/backup_n8n.sh](../scripts/backup_n8n.sh) |

### ⏳ Fase 2 — Em Roadmap

**PLANO_IMPLEMENTACAO_2026-04-29.md** detalha:

1. **Feedback Loop (Prioridade: ALTA)**
   - Endpoint: `POST /api/contestacoes/{id}/feedback`
   - Marcar como "útil" / "não útil"
   - Alimentar re-ranking de RAG (60% sim + 40% nota)

2. **Few-shot Examples (Prioridade: ALTA)**
   - Tabela `contestacoes_exemplares` curada pelo time
   - Injetar 3-5 exemplos no system prompt do Claude
   - Impacto: +15-20% qualidade de tese central

3. **Jurisprudência em Tempo Real (Prioridade: MÉDIA)**
   - Integrar com Jusbrasil API ou STJ/STF públicos
   - Buscar acórdãos similares antes de chamar Claude
   - Inserir no contexto: "Decisões recentes relevantes: ..."

4. **Persistência DOCX Nativa (Prioridade: BAIXA)**
   - Gerar `.docx` no backend (python-docx)
   - Salvar em S3/MinIO para downloads
   - Substituir base64 por URL pré-assinada

5. **Migração PostgreSQL para n8n (Prioridade: OPERACIONAL)**
   - Trocar SQLite por PostgreSQL dedicado
   - Implementar backups automáticos
   - Alta disponibilidade multi-worker

### 📌 Ações Imediatas

**Para Desenvolvimento Local:**
```bash
# 1. Fazer backup antes de qualquer mudança
./scripts/backup_n8n.sh

# 2. Rodar testes para validar ambiente
cd Backend && python -m pytest -v

# 3. Revisar logs do n8n
docker compose logs -f n8n | tail -100

# 4. Testar workflow manualmente
curl -X POST http://localhost:5678/webhook/contestacao-claude \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

**Para Produção:**
```bash
# 1. Ativar segurança n8n
export N8N_BLOCK_ENV_ACCESS_IN_NODE=true

# 2. Agendar backups
BACKUP_DIR=/mnt/backups/n8n ./scripts/backup_n8n.sh --schedule

# 3. Configurar alertas (Sentry, DataDog)
export SENTRY_DSN=https://...
export DATADOG_API_KEY=...

# 4. Deploy com CI/CD
git push main  # Dispara GitHub Actions
```

---

## ⚡ Referência Rápida de Comandos

### Docker & Compose

```bash
# Iniciar stack completa
docker compose up -d

# Ver logs em tempo real
docker compose logs -f backend n8n

# Parar e remover
docker compose down

# Backup do n8n
./scripts/backup_n8n.sh

# Restaurar backup
./scripts/backup_n8n.sh --restore ./n8n_backup_YYYYMMDD.tar.gz
```

### Backend FastAPI

```bash
# Rodar testes
cd Backend && python -m pytest -v --cov=App --cov-report=html

# Iniciar servidor dev
python main.py

# Ver health checks
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

### Frontend Vite

```bash
# Instalar dependências
cd "Front end/vite-project" && npm install

# Dev server
npm run dev  # http://localhost:5173

# Build produção
npm run build

# Deploy Vercel
npm install -g vercel
vercel --prod
```

### n8n Workflows

```bash
# Acessar interface
http://localhost:5678

# Importar workflow
→ Menu → Import Workflow → docs/n8n_workflow_*.json

# Ativar webhook
→ Workflow → Trigger → Copy Webhook URL

# Ver execuções
curl -H "X-N8N-API-KEY: $N8N_API_KEY" \
  http://localhost:5678/api/v1/executions
```

---

## 📞 Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| **n8n não responde** | `docker compose restart n8n` → aguardar healthz |
| **Timeout Claude** | Aumentar `CLAUDE_TIMEOUT_MS=300000` no .env |
| **Rate limit 429** | Implementado retry automático (3× backoff) |
| **Banco SQLite travado** | `docker compose restart n8n` limpa lock |
| **Workflows sumiram** | `./scripts/backup_n8n.sh --restore <arquivo>` |
| **Testes falhando** | Verificar `.env` → confere credenciais Supabase |
| **OCR não funciona** | Tesseract instalado no Dockerfile? `docker compose rebuild` |

---

## 📚 Referências Importantes

### Documentação Interna

- **[ENTREGA_FINAL.md](./ENTREGA_FINAL.md)** — Entregáveis da Etapa 5
- **[REVISAO_2026-04-29.md](./REVISAO_2026-04-29.md)** — Issues resolvidas
- **[AGENTE_IA_AUTOJURI.md](./AGENTE_IA_AUTOJURI.md)** — Qualidade IA por área
- **[OPERACOES_N8N.md](./OPERACOES_N8N.md)** — Deploy, segurança, backup
- **[PLANO_IMPLEMENTACAO_2026-04-29.md](./PLANO_IMPLEMENTACAO_2026-04-29.md)** — Roadmap Fase 1 e 2

### Documentação Externa

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [n8n Docs](https://docs.n8n.io)
- [Supabase Docs](https://supabase.com/docs)
- [Anthropic Claude API](https://docs.anthropic.com)
- [PostgreSQL pgvector](https://github.com/pgvector/pgvector)

---

## 🔐 Segurança & Compliance

### OWASP Top 10 (Implementado)

✅ **A01: Broken Access Control** — JWT + bearer token opaco  
✅ **A02: Cryptographic Failures** — PBKDF2 + HTTPOnly cookies  
✅ **A03: Injection** — SQL parametrizado + Pydantic validation  
✅ **A04: Insecure Design** — Rate limiting + timeout  
✅ **A05: Broken Authentication** — 2FA ready (Supabase Auth)  
✅ **A06: Vulnerable Components** — Dependências pinadas em requirements.txt  
⚠️ **A07: Identification/Auth** — PBKDF2 120k → roadmap 600k  
✅ **A08: Data Integrity** — Auditoria completa em n8n_response  

### Credenciais & Secrets

```bash
# NUNCA commitar em repositório
.env                  # Expirado? Rotacionar!
Frontend/Supabase Key # Pública por design
ANTHROPIC_API_KEY     # CRÍTICO: rotacionar se exposto

# Usar secret manager em produção
Railway Secrets
Vercel Environment Variables
AWS Secrets Manager
```

---

## 📊 Métricas Finais (Etapa 5)

| Métrica | Valor | Status |
|---------|-------|--------|
| Testes Backend | 269 passed, 0 failed | ✅ |
| Cobertura Backend | 74% statements | ✅ |
| Cobertura Frontend | 84% statements, 91% branches | ✅ |
| Complexidade Ciclomática | 3.54 (A) | ✅ Excelente |
| PRs Entregues | 3 (frontend, backend, n8n) | ✅ |
| Workflows CI/CD | 5 (ci, cd, frontend, lint, security) | ✅ |

---

**Última atualização:** 28/05/2026  
**Versão documento:** 1.0  
**Mantido por:** Equipe AutoJuri

