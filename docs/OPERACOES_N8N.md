# Guia de Operações — n8n & Backup

**Última atualização:** 28/05/2026  
**Versão n8n:** 2.17.5  
**Status:** Pronto para Produção

---

## 📋 Sumário

1. [Backup & Restauração](#backup--restauração)
2. [Segurança](#segurança)
3. [Monitoramento](#monitoramento)
4. [Troubleshooting](#troubleshooting)

---

## Backup & Restauração

### Por que fazer backup?

O n8n armazena **todos** os workflows, credenciais e histórico de execução no banco de dados SQLite (volume Docker `autojuri_n8n_data`). Perda desse volume = perda completa dos workflows e credenciais.

### Backup Automático Recomendado

**Em Produção:** Migre para PostgreSQL dedicado (veja [Configuração PostgreSQL](#configuração-postgresql))

**Em Dev/Teste:** Use o script de backup incluído

```bash
# Fazer backup manual agora
cd /caminho/do/projeto
./scripts/backup_n8n.sh

# Agendar backup automático diário às 02:00
BACKUP_DIR=/mnt/backups ./scripts/backup_n8n.sh --schedule

# Listar backups disponíveis
./scripts/backup_n8n.sh --list

# Limpar backups com mais de 30 dias
./scripts/backup_n8n.sh --cleanup 30

# Restaurar de um backup específico
./scripts/backup_n8n.sh --restore ./n8n_backup_20260528_140000.tar.gz
```

### Backup Manual via Docker

```bash
# Backup direto
docker run --rm \
  -v autojuri_n8n_data:/data \
  -v $(pwd):/backup \
  busybox tar czf /backup/n8n_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restaurar
docker run --rm \
  -v autojuri_n8n_data:/data \
  -v $(pwd):/backup \
  busybox tar xzf /backup/n8n_backup_YYYYMMDD_HHMMSS.tar.gz -C /data
```

---

## Segurança

### ✅ Checklist de Segurança do n8n

| Item | Status | Nota |
|------|--------|------|
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | ✅ `true` | Impede acesso a credenciais via Code nodes |
| Workflows importados do `.json` | ⚠️ Revisar | Sempre audite antes de ativar em prod |
| Credenciais do Anthropic | 🔐 Vaulted | Nunca expor em logs ou respostas HTTP |
| Banco SQLite sem backup | ❌ **Crítico** | Configure cron ou PostgreSQL |
| HTTPS para webhooks | ⚠️ Em dev | Configurar em produção com `N8N_WEBHOOK_URL=https://...` |

### Variáveis de Ambiente Críticas

```bash
# Sempre defina em produção
N8N_BLOCK_ENV_ACCESS_IN_NODE=true
N8N_SECURE_COOKIE=true
N8N_AUTH_EXCLUDE_ENDPOINTS=healthz

# Nunca comente ou deixe em branco
N8N_WEBHOOK_AUTH_TOKEN=<gere-com-secrets.token_hex(32)>
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### Rotação de Credenciais

Se alguma credencial foi exposta:

```bash
# 1. Regenerar token n8n
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Atualizar N8N_WEBHOOK_AUTH_TOKEN no .env

# 3. Recriar o container
docker compose down
docker compose up -d

# 4. Rotacionar chave Anthropic
# → https://console.anthropic.com/account/api-keys

# 5. Audit logs do n8n
docker compose logs n8n | grep -i "auth\|credential"
```

---

## Configuração PostgreSQL

Para produção com múltiplos workers ou alta disponibilidade:

### 1. Provisionar banco PostgreSQL

```sql
-- Em um servidor PostgreSQL separado
CREATE DATABASE n8n;
CREATE USER n8n_user WITH PASSWORD 'senha_forte_aqui';
GRANT ALL PRIVILEGES ON DATABASE n8n TO n8n_user;
```

### 2. Atualizar docker-compose.yml

```yaml
  n8n:
    environment:
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres.seudominio.com
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=n8n_user
      - DB_POSTGRESDB_PASSWORD=${N8N_POSTGRES_PASSWORD}
      - DB_POSTGRESDB_SSL=true
```

### 3. Atualizar .env

```bash
N8N_POSTGRES_PASSWORD=senha_forte_aqui
# Backup automático PostgreSQL
pg_dump -h postgres.seudominio.com -U n8n_user -d n8n > n8n_backup_$(date +%Y%m%d).sql
```

---

## Monitoramento

### Health Checks

```bash
# Verificar saúde do n8n
curl -s http://localhost:5678/healthz | jq .

# Ver logs em tempo real
docker compose logs -f n8n

# Contar execuções de workflows
curl -s http://localhost:5678/api/v1/executions \
  -H "X-N8N-API-KEY: $(grep N8N_API_KEY .env)" | jq '.data | length'
```

### Alertas Recomendados

| Evento | Ação |
|--------|------|
| n8n não responde por 5 min | Reiniciar container + verificar logs |
| Volume `autojuri_n8n_data` > 80% | Fazer backup + limpar execuções antigas |
| Erro 429 Anthropic (rate limit) | Aumentar `CLAUDE_TIMEOUT_MS`, implementar fila |
| Webhook retorna 500 | Verificar logs: `docker compose logs n8n \| tail -50` |

---

## Troubleshooting

### Problema: "Volume not found"

```bash
# Recriar volume
docker volume create autojuri_n8n_data
docker compose up -d n8n
```

### Problema: "Database locked" (SQLite)

```bash
# Reiniciar n8n para limpar lock
docker compose restart n8n

# Ou fazer backup → limpar → restaurar
docker compose stop n8n
docker volume rm autojuri_n8n_data
docker volume create autojuri_n8n_data
docker run --rm -v autojuri_n8n_data:/data -v $(pwd):/backup \
  busybox tar xzf /backup/n8n_backup_latest.tar.gz -C /data
docker compose start n8n
```

### Problema: "Timeout connecting to Anthropic"

```bash
# Aumentar timeout
export CLAUDE_TIMEOUT_MS=300000  # 5 minutos
docker compose down && docker compose up -d

# Ou adicionar retry ao Node code:
// No Code node do workflow, usar callClaudeWithRetry()
// que já implementa 3 retries com backoff exponencial
```

### Problema: Workflows desaparecidos após restart

**Causa:** Volume Docker não foi salvo ou backup não foi restaurado

**Solução:**

```bash
# 1. Verificar se volume existe
docker volume ls | grep autojuri_n8n_data

# 2. Se volume existe mas workflows sumiram:
docker run --rm \
  -v autojuri_n8n_data:/data \
  busybox find /data -name "*.json" | head -10

# 3. Se vazio, restaurar do backup
./scripts/backup_n8n.sh --restore ./n8n_backup_20260520.tar.gz

# 4. Se sem backup anterior, reimportar workflows
# → Interface do n8n: Import Workflow → docs/n8n_workflow_*.json
```

---

## Checklist de Deploy em Produção

- [ ] `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`
- [ ] `N8N_SECURE_COOKIE=true`
- [ ] `N8N_WEBHOOK_AUTH_TOKEN` setada (gere novo token)
- [ ] `ANTHROPIC_API_KEY` rotacionada
- [ ] PostgreSQL provisionado e testado
- [ ] Backup diário agendado (`cron`)
- [ ] Logs centralizados (Sentry, CloudWatch, ELK)
- [ ] Monitoramento de alertas (PagerDuty, etc.)
- [ ] DNS configurado para `N8N_WEBHOOK_URL`
- [ ] HTTPS/TLS habilitado
- [ ] Plano de disaster recovery documentado

---

## Links Úteis

- [n8n Docs](https://docs.n8n.io)
- [n8n Security Best Practices](https://docs.n8n.io/hosting/scaling/security/)
- [PostgreSQL Backup & Restore](https://www.postgresql.org/docs/current/backup.html)
- [Docker Volumes](https://docs.docker.com/storage/volumes/)
- [AutoJuri — PLANO_IMPLEMENTACAO_2026-04-29](./PLANO_IMPLEMENTACAO_2026-04-29.md)

