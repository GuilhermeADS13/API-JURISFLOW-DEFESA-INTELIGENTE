# Deploy do backend AutoJuri

Guia para colocar **só o backend** no ar. O resto já está pronto:

| Camada   | Onde                | Status |
|----------|---------------------|--------|
| Banco    | Supabase            | ✅ no ar |
| Frontend | Vercel              | ✅ no ar |
| Backend  | (a decidir)         | ⛔ falta |

O frontend do Vercel hoje é uma "casca": ele carrega, mas as chamadas à API
falham porque não existe backend público pra ele conversar. Este guia resolve
isso. **Nada aqui altera o ambiente local** (`docker-compose.yml` e
`Backend/Dockerfile` continuam intactos) — são arquivos e passos adicionais.

---

## 0. Os 2 ajustes que valem pra QUALQUER caminho (já aplicados no repo)

Independente de onde o backend rodar (VPS ou HF), o front precisa achar o
backend e o backend precisa liberar o front no CORS. Isso já foi ajustado:

1. **CORS (backend libera o front do Vercel).**
   `docker-compose.yml` agora tem no default:
   `FRONTEND_ORIGINS=http://localhost:5173,https://jurisflow-contestacao.vercel.app`.
   Ou seja, o mesmo compose num VPS já libera o front sem você setar nada. Se o
   domínio do Vercel mudar, sobrescreva `FRONTEND_ORIGINS` no `.env`.

2. **Front aponta pro backend (uma linha só).**
   `Front end/vite-project/.env.production` tem **uma** variável a trocar:

   ```env
   VITE_API_BASE_URL=https://SEU_BACKEND_PUBLICO/api
   ```

   Troque `https://SEU_BACKEND_PUBLICO/api` pela URL pública do backend (com
   `/api` no fim) **depois** de escolher o host, e dê `git push`. O Vercel
   rebuilda sozinho (CD) e o front passa a falar com o backend. Todos os outros
   endpoints derivam dessa base automaticamente
   (`Front end/vite-project/src/config/api.js`), então é literalmente 1 linha.

   > ⚠️ Não passe `VITE_API_BASE_URL` como secret no GitHub Actions: um secret
   > vazio sobrescreve o `.env.production` com `""` (testado). A fonte única de
   > verdade é o `.env.production`.

---

## Qual caminho escolher?

| Critério              | **A) VPS (~US$5/mês)**            | **B) HF Spaces (grátis)**              |
|-----------------------|----------------------------------|----------------------------------------|
| Esforço               | Baixo (roda o compose que já existe) | Alto (imagem única nova, não testada) |
| Robustez              | Alta                             | Frágil (storage efêmero, dorme em 48h) |
| Persistência do n8n   | Volume Docker (persiste)         | Efêmera (re-importa workflow a cada boot) |
| Sempre acordado       | Sim                              | Não (dorme sem tráfego; acorda lento)  |
| Custo                 | ~US$5/mês (ex: Hetzner CX22)     | US$0 (persistência paga ~US$5/mês)     |
| Recomendado           | **Sim** ✅                        | Só pra teste/POC                        |

**Recomendação:** VPS. Ele roda o `docker-compose.yml` que você já usa e testa
localmente, sem adaptação — é o caminho de menor risco.

---

## Caminho A — VPS (recomendado)

Roda o **mesmo** `docker compose up -d` do seu local, com um proxy na frente pra
dar HTTPS. Nada de imagem nova.

### Atalho turnkey (script automatiza A.2–A.6)
Depois de ter o VPS, o DNS apontado e o repo clonado com o `.env` preenchido:
```bash
cd autojuri                       # raiz do repo, no VPS
cp .env.example .env && nano .env # preencha os segredos (só na 1ª vez)
bash scripts/deploy/vps_setup.sh api.seu-dominio.com --firewall
```
O `scripts/deploy/vps_setup.sh` é idempotente e faz: instala Docker, sobe
backend+n8n, importa/ativa os 4 workflows, instala o Caddy com HTTPS pro seu
domínio e (com `--firewall`) configura o ufw de forma SSH-safe. Ele imprime no
fim o único passo que sobra (setar `VITE_API_BASE_URL` no Vercel).

Se preferir entender/rodar passo-a-passo, siga A.1–A.7 abaixo (é o que o script faz).

### A.1 Provisionar o VPS
- Contrate um VPS com **4–8 GB de RAM** (o backend puxa torch/LibreOffice/Chromium).
  Ex: Hetzner CX22, DigitalOcean, Contabo. Ubuntu 22.04/24.04.
- Aponte um subdomínio pro IP do VPS: registro DNS **A** `api.seu-dominio.com → <IP>`.

### A.2 Instalar Docker + Compose
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker   # opcional: rodar sem sudo
```

### A.3 Subir o backend + n8n
```bash
# Repo privado: use um Personal Access Token ou deploy key. Ex com PAT:
git clone https://github.com/GuilhermeADS13/API-JURISFLOW-DEFESA-INTELIGENTE.git autojuri && cd autojuri
cp .env.example .env
nano .env     # preencha DATABASE_*, SUPABASE_*, ANTHROPIC_API_KEY, BACKEND_ADMIN_TOKEN, ADMIN_EMAILS...
docker compose up -d backend n8n     # NÃO suba o serviço 'frontend' no VPS (o front está no Vercel)
```

Ajustes recomendados no `.env` do VPS (produção atrás de proxy HTTPS):
```env
SESSION_COOKIE_SECURE=true
RATE_LIMIT_TRUST_FORWARDED=true
N8N_BLOCK_ENV_ACCESS_IN_NODE=false   # workflows leem ANTHROPIC_API_KEY via process.env (dev/atual)
# Se o front (vercel.app) e o backend (api.seu-dominio.com) forem cross-site e você
# depender do cookie de sessão HTTPOnly, use também:
# SESSION_COOKIE_SAMESITE=none
```

### A.4 Importar e ativar os workflows do n8n
O n8n sobe vazio. Rode o script (usa a CLI do n8n dentro do container — funciona
numa instância nova, sem API key):
```bash
bash scripts/deploy/import_n8n_workflows.sh
```
Ele importa os 4 JSONs (`docs/n8n_workflow_*.json`) e ativa todos (registra os
webhooks + o schedule semanal). Alternativa manual: importar pela UI
(`http://<IP>:5678`, atrás de SSH tunnel — ver A.6).

### A.5 HTTPS com Caddy
Use o **`Caddyfile`** que está na raiz do repo (troque `api.seu-dominio.com`).
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
sudo cp Caddyfile /etc/caddy/Caddyfile      # após editar o subdomínio
sudo systemctl reload caddy
```
Caddy pega o certificado Let's Encrypt sozinho. Teste:
`curl https://api.seu-dominio.com/health` → `{"status":"ok"}` (ou equivalente).

### A.6 Firewall (importante)
O compose publica o n8n em `:5678` no host — **não deixe isso aberto na internet**.
O backend fala com o n8n pela rede interna do Docker (`http://n8n:5678`), então
`:5678` não precisa estar público.
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable        # bloqueia 5678/8000 de fora; acesse o n8n via SSH tunnel:
# no seu PC:  ssh -L 5678:localhost:5678 usuario@<IP>  -> abra http://localhost:5678
```
(Alternativa: expor o n8n num subdomínio com basic auth — bloco comentado no `Caddyfile`.)

### A.7 Ligar o front no backend
Edite `Front end/vite-project/.env.production`:
```env
VITE_API_BASE_URL=https://api.seu-dominio.com/api
```
`git push` → Vercel rebuilda → pronto. Teste ponta-a-ponta: abra o front do
Vercel, faça login e gere uma contestação.

### A.8 (variante) Oracle Cloud Always Free — ARM, grátis pra sempre
A stack já é **multi-arch**: o `Backend/Dockerfile` detecta ARM e instala o torch
certo (no x86 nada muda). O n8n, Playwright/Chromium, LibreOffice e tesseract têm
build arm64. Então roda no Ampere A1 sem mágica — só com estes cuidados de Oracle:

0. **Upgrade pra Pay As You Go (PAYG) — NÃO pule.** O Always Free **puro** recupera
   (deleta) instâncias ociosas: se em 7 dias o CPU ficar <20%, a Oracle pode
   reclamar a máquina — e um backend fica ocioso quase sempre. O upgrade pra PAYG
   **desliga essa reclamação** e você **continua pagando US$0** enquanto ficar
   dentro dos limites free. Console OCI → **Billing & Cost Management → Upgrade
   and Manage Payment → Upgrade to Pay As You Go** → cadastre um cartão.
   - **Ficar US$0:** use **1 instância A1 dentro de 4 OCPU / 24 GB** e o boot
     volume padrão (~50 GB, dentro dos 200 GB free), **1 IP público**. Não passe
     disso que não há cobrança.
   - **Trava de segurança:** crie um **Budget alert** (Billing → Budgets →
     Create Budget, valor ~US$1, alerta em 100%). Se algo um dia começar a
     custar, você recebe email na hora — nunca é pego de surpresa.

1. **Criar a instância.** Shape `VM.Standard.A1.Flex` (Ampere ARM). O Always Free
   dá até **4 OCPU + 24 GB RAM** de graça — pegue pelo menos **2 OCPU / 12 GB**.
   Imagem: **Canonical Ubuntu 22.04 (aarch64)**.
   > ⚠️ É comum dar **"Out of capacity"** ao criar A1 (muita gente disputa o free).
   > Tente outra Availability Domain, outra região, ou repita depois. Persista.

2. **Abrir as portas — o gotcha nº1 do Oracle (2 camadas).**
   - **Security List da VCN** (console OCI → Networking → VCN → Security List):
     adicione ingress TCP **80** e **443** (source `0.0.0.0/0`). O 22 já vem aberto.
   - **iptables da VM** (a imagem Ubuntu do Oracle só libera 22 e tem REJECT no fim):
     ```bash
     bash scripts/deploy/oracle_open_ports.sh
     ```
   Sem as duas camadas, o Caddy sobe mas dá "connection refused" de fora.

3. **Rodar o setup — SEM `--firewall`** (não use o ufw no Oracle; ele conflita com
   o iptables pré-instalado da imagem):
   ```bash
   git clone https://github.com/GuilhermeADS13/API-JURISFLOW-DEFESA-INTELIGENTE.git autojuri && cd autojuri
   cp .env.example .env && nano .env
   bash scripts/deploy/oracle_open_ports.sh          # camada 2 do firewall
   bash scripts/deploy/vps_setup.sh api.seu-dominio.com   # note: SEM --firewall
   ```

4. **DNS:** com 24 GB de RAM sobra folga, mas você ainda precisa de um domínio
   apontando pro **IP público** da instância (registro A). Sem domínio, use um
   subdomínio grátis (DuckDNS) — Caddy não emite certificado pra IP puro.

O resto (A.7 acima) é igual: `VITE_API_BASE_URL` no `.env.production` + push.

---

## Caminho B — Hugging Face Spaces (grátis, experimental)

> ⚠️ **Não validado end-to-end** (não há ambiente HF aqui). Frágil por natureza:
> storage efêmero e sleep. Bom pra POC, não pra uso sério. Se der trabalho,
> volte pro VPS.

Coloca backend + n8n **no mesmo container** (o HF só expõe 1 porta: 7860).
Arquivos novos, sem tocar no local:
- `Backend/Dockerfile.hf` — imagem única (Python + Node/n8n).
- `Backend/deploy/hf_entrypoint.sh` — a cada boot: re-importa/ativa workflows,
  sobe n8n interno (:5678) e o backend público (:7860).

### B.1 Testar a imagem localmente (opcional, recomendado antes do HF)
```bash
# a partir da RAIZ do repo (contexto precisa de Backend/ e docs/):
docker build -f Backend/Dockerfile.hf -t autojuri-hf .
docker run -p 7860:7860 --env-file .env autojuri-hf
curl http://localhost:7860/health
```

### B.2 Criar o Space
- huggingface.co → New Space → **SDK: Docker** → Blank.
- Copie `Backend/Dockerfile.hf` para a **raiz do Space** com o nome `Dockerfile`
  (o HF exige esse nome), junto com `Backend/` e `docs/` (o build precisa deles).
- Em **Settings → Variables and secrets**, coloque as mesmas variáveis do `.env`
  (`DATABASE_*`, `SUPABASE_*`, `ANTHROPIC_API_KEY`, `BACKEND_ADMIN_TOKEN`,
  `ADMIN_EMAILS`, etc.). As sensíveis vão em **Secrets**.

### B.3 Detalhes que costumam quebrar no HF
- **Storage efêmero:** o SQLite do n8n some no restart. O `hf_entrypoint.sh`
  re-importa os workflows a cada boot via `n8n import:workflow`. Se o formato dos
  JSONs (`docs/*.json`) não for o de *export* do n8n, o import CLI pode falhar —
  nesse caso importe 1x pela UI e re-exporte no formato CLI, ou use a REST API.
- **Sleep:** o Space dorme após ~48h sem tráfego; a 1ª request acorda (lenta).
  Um ping periódico (cron externo) ajuda a manter acordado.
- **Modelo de embedding:** re-baixa ~120 MB após cada restart (cache efêmero).

### B.4 Ligar o front no backend
Edite `Front end/vite-project/.env.production`:
```env
VITE_API_BASE_URL=https://SEU-USUARIO-NOME-DO-SPACE.hf.space/api
```
`git push` → Vercel rebuilda.

---

## Checklist final (qualquer caminho)
- [ ] Backend público responde em `https://.../health`.
- [ ] `.env.production` → `VITE_API_BASE_URL` com a URL real + `/api`, e push feito.
- [ ] `FRONTEND_ORIGINS` do backend inclui o domínio do Vercel (já no default).
- [ ] n8n com os 4 workflows importados e **ativos**.
- [ ] Teste ponta-a-ponta: login no front do Vercel + gerar uma contestação real.
