# Migrations Supabase

Migrations aplicadas via Supabase MCP (`apply_migration`) e versionadas aqui pra ter histórico fora do banco. Ordem cronológica:

| Versão (timestamp UTC) | Nome | Categoria |
|---|---|---|
| `20260604164243` | revoke_rls_auto_enable_from_public_roles | 🔴 segurança |
| `20260604164246` | add_index_usuarios_sessoes_usuario_id | 🟠 performance |
| `20260604164248` | rls_policies_baseline_5_tables | 🟠 segurança / docs |
| `20260604164347` | deny_public_access_to_configuracoes | 🟠 segurança / docs |
| `20260605000000` | add_fatos_tsv_for_hybrid_rag_search | 🟢 feature / RAG |
| `20260605120000` | add_metadados_juridicos_contestacoes | 🟢 feature / metadados |
| `20260605130000` | add_ocr_cache_table | 🟢 feature / performance |
| `20260605140000` | add_legislacao_table | 🟢 feature / RAG legislação |

## Reaplicar em outro ambiente

### Via MCP do Supabase (recomendado)

Com o MCP do Supabase configurado (`@supabase/mcp-server-supabase`), pedir ao Claude pra aplicar cada arquivo `.sql` deste diretório em ordem via `apply_migration`.

### Via Supabase CLI

```bash
# Pré-requisito: supabase CLI instalado e autenticado
supabase link --project-ref <seu-project-ref>

# Aplicar cada migration manualmente
psql $DATABASE_URL -f 20260604164243_revoke_rls_auto_enable_from_public_roles.sql
psql $DATABASE_URL -f 20260604164246_add_index_usuarios_sessoes_usuario_id.sql
psql $DATABASE_URL -f 20260604164248_rls_policies_baseline_5_tables.sql
psql $DATABASE_URL -f 20260604164347_deny_public_access_to_configuracoes.sql
```

### Baseline schema (CREATE TABLE original)

O schema das tabelas (`contestacoes`, `usuarios`, `usuarios_sessoes`, etc) **não está aqui** porque foi criado antes do versionamento começar. Pra dump completo:

```bash
supabase db dump --schema public > 20260604000000_baseline.sql
```

E adicionar como primeira migration (deve rodar antes das demais).

## Source of truth

A tabela `supabase_migrations.schema_migrations` no banco é o source of truth — `apply_migration` registra lá automaticamente. Os arquivos aqui são pra git/code-review/onboarding.
