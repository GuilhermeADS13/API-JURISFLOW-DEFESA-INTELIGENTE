#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — bootstrap do backend num VPS Ubuntu (Caminho A do docs/deploy_backend.md)
#
# Roda o MESMO docker-compose do local (backend + n8n) e poe o Caddy na frente
# pra HTTPS automatico. NAO altera nada do ambiente local — e um script pra rodar
# NO VPS, depois de clonar o repo e preencher o .env.
#
# PRE-REQUISITOS (feitos por VOCE, o script confere):
#   1) Um VPS Ubuntu 22.04/24.04 com 4-8 GB de RAM.
#   2) DNS: registro A do seu subdominio -> IP do VPS  (ex: api.seu-dominio.com).
#   3) Repo ja clonado e voce esta na raiz dele.
#   4) .env preenchido (cp .env.example .env && edite os segredos).
#
# USO (na raiz do repo, no VPS):
#   bash scripts/deploy/vps_setup.sh api.seu-dominio.com              # sem firewall
#   bash scripts/deploy/vps_setup.sh api.seu-dominio.com --firewall   # tambem configura ufw
#
# IDEMPOTENTE: pode rodar de novo; pula o que ja esta feito.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="${1:-}"
DO_FIREWALL="no"
[[ "${2:-}" == "--firewall" ]] && DO_FIREWALL="yes"

log()  { printf '\033[1;36m[vps]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[vps][aviso]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[vps][erro]\033[0m %s\n' "$*" >&2; exit 1; }

# ── 0. Validacoes ────────────────────────────────────────────────────────────
[[ -n "$DOMAIN" ]] || die "informe o subdominio. Ex: bash scripts/deploy/vps_setup.sh api.seu-dominio.com"
[[ "$DOMAIN" =~ ^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] || die "dominio invalido: '$DOMAIN'"
[[ -f docker-compose.yml ]] || die "rode este script na RAIZ do repo (nao achei docker-compose.yml aqui)."
[[ -f .env ]] || die ".env nao encontrado. Faca 'cp .env.example .env' e preencha os segredos antes."

# confere que os segredos criticos nao estao vazios (sem imprimir valores)
for k in DATABASE_HOST SUPABASE_URL ANTHROPIC_API_KEY BACKEND_ADMIN_TOKEN; do
	if ! grep -qE "^${k}=.+" .env; then
		warn "$k parece vazio/ausente no .env — o backend pode nao subir corretamente."
	fi
done

# ── 1. Docker ────────────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
	log "Docker ja instalado ($(docker --version))."
else
	log "Instalando Docker..."
	curl -fsSL https://get.docker.com | sh
	sudo usermod -aG docker "$USER" || true
	warn "Adicionei seu usuario ao grupo docker. Se der 'permission denied', saia e entre no SSH de novo (ou rode com sudo)."
fi

# ── 2. Ajustes de .env recomendados p/ producao atras de proxy ───────────────
ensure_env() { # ensure_env CHAVE VALOR — seta se ausente; nao sobrescreve se ja existir
	local key="$1" val="$2"
	if grep -qE "^${key}=" .env; then
		log ".env: $key ja definido (mantido)."
	else
		printf '%s=%s\n' "$key" "$val" >> .env
		log ".env: adicionei $key=$val"
	fi
}
log "Garantindo flags de producao no .env (nao sobrescreve o que ja existe)..."
ensure_env SESSION_COOKIE_SECURE true
ensure_env RATE_LIMIT_TRUST_FORWARDED true
ensure_env FRONTEND_ORIGINS "http://localhost:5173,https://jurisflow-contestacao.vercel.app"

# ── 3. Subir backend + n8n (NAO o frontend — ele esta no Vercel) ─────────────
log "Buildando e subindo backend + n8n (pode levar alguns minutos na 1a vez)..."
docker compose up -d --build backend n8n

log "Aguardando o backend ficar saudavel..."
for _ in $(seq 1 60); do
	if docker exec autojuri_backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
		log "Backend saudavel."; break
	fi
	sleep 3
done

# ── 4. Importar + ativar os 4 workflows do n8n ───────────────────────────────
log "Importando/ativando workflows do n8n..."
bash scripts/deploy/import_n8n_workflows.sh || warn "import de workflows falhou — rode manualmente depois: bash scripts/deploy/import_n8n_workflows.sh"

# ── 5. Caddy (HTTPS automatico) ──────────────────────────────────────────────
if command -v caddy >/dev/null 2>&1; then
	log "Caddy ja instalado."
else
	log "Instalando Caddy..."
	sudo apt-get update
	sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
	sudo apt-get update
	sudo apt-get install -y caddy
fi

log "Escrevendo /etc/caddy/Caddyfile para o dominio $DOMAIN..."
sudo mkdir -p /var/log/caddy
# gera o Caddyfile a partir do template do repo, trocando o placeholder pelo dominio real
sed "s/api\.seu-dominio\.com/${DOMAIN}/g" Caddyfile | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl reload caddy || sudo systemctl restart caddy

# ── 6. Firewall (opcional, SSH-safe) ─────────────────────────────────────────
if [[ "$DO_FIREWALL" == "yes" ]]; then
	if command -v ufw >/dev/null 2>&1; then
		warn "Configurando ufw. Liberando 22/80/443 ANTES de habilitar (pra nao derrubar seu SSH)."
		sudo ufw allow 22/tcp
		sudo ufw allow 80/tcp
		sudo ufw allow 443/tcp
		sudo ufw --force enable
		log "Firewall ativo. As portas 8000/5678 ficam bloqueadas de fora (acesse o n8n via SSH tunnel)."
	else
		warn "ufw nao instalado — pulei o firewall. Instale com 'sudo apt install ufw' e rode de novo com --firewall."
	fi
else
	warn "Firewall NAO configurado. As portas 8000 e 5678 do compose ficam ABERTAS na internet."
	warn "Rode de novo com --firewall, ou configure ufw manualmente (libere 22/80/443, bloqueie o resto)."
fi

# ── Final ────────────────────────────────────────────────────────────────────
log "─────────────────────────────────────────────────────────────"
log "Backend no ar atras do Caddy. Teste (aguarde o cert Let's Encrypt ~30s):"
log "   curl https://${DOMAIN}/health"
log ""
log "FALTA 1 passo (no seu PC, nao aqui):"
log "   Front end/vite-project/.env.production -> VITE_API_BASE_URL=https://${DOMAIN}/api"
log "   git push  (o Vercel rebuilda e o front passa a falar com este backend)"
log "─────────────────────────────────────────────────────────────"
