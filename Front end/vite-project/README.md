# Frontend (React + Vite)

Interface do sistema de automacao de contestacao.

## Rodar localmente

```bash
cd "Front end/vite-project"
npm install
npm run dev
```

## Scripts

- `npm run dev` - ambiente de desenvolvimento
- `npm run build` - build de producao
- `npm run preview` - preview local do build
- `npm run lint` - validacao eslint
- `npm run test` - executa testes unitarios (Vitest)
- `npm run test:watch` - modo watch de testes

## Variaveis de ambiente

Crie um `.env` (ou `.env.local`) em `vite-project` quando precisar sobrescrever:

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_IA_ENDPOINT=http://localhost:8000/api/gerar-contestacao
VITE_DASHBOARD_SUMMARY_ENDPOINT=http://localhost:8000/api/contestacoes/resumo
VITE_SUPPORT_CONTACT_ENDPOINT=http://localhost:8000/api/suporte/contato
VITE_SUPABASE_URL=https://seu-projeto.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxxxxxxxxxxxxxxxxxxx
```

## Notas de arquitetura

- Autenticacao do usuario (cadastro/login/logout/sessao) usa Supabase Auth no frontend.
- Envio do caso inclui metadados + conteudo base64 do arquivo base.
- Chamadas para backend enviam `Authorization: Bearer <access_token_supabase>` quando sessao estiver ativa.
- Dashboard e historico agora sincronizam dados reais no endpoint `GET /api/contestacoes/resumo`.
- Endpoint do agente de IA e endpoint de suporte seguem configurados via `VITE_API_BASE_URL`.
- Validacao de numero de processo no front segue regex CNJ do backend.

## Conectar Supabase

1. No painel do Supabase, abra `Connect` e copie:
- `Project URL`
- `Publishable key` (ou `anon key` legado)

2. Preencha essas chaves no `.env.local`.

3. Use o client centralizado em `src/lib/supabaseClient.js`:

```js
import { getSupabaseClient } from "./lib/supabaseClient";

const supabase = getSupabaseClient();
const { data, error } = await supabase.from("sua_tabela").select("*").limit(10);
```

4. Reinicie o `npm run dev` apos alterar o `.env.local`.
