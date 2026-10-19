#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — dispara o scrape de jurisprudencia (TST + CARF) no backend.
# Substitui o workflow n8n "Scrape Jurisprudencia Agendado" no VPS, onde o n8n
# nao tem a credential httpHeaderAuth (so a API REST a cria).
#
# Uso (na raiz do repo, no VPS):
#   bash scripts/deploy/scrape_cron.sh             # dispara uma vez agora
#   bash scripts/deploy/scrape_cron.sh --instalar  # agenda no crontab do usuario
#
# Horarios = os do n8n: Dom 03h e Seg/Sex 15h (Brasilia). O cron do Ubuntu roda
# em UTC e Brasilia e UTC-3 (sem horario de verao): Dom 06h e Seg/Sex 18h UTC.
# O token e lido do .env a cada execucao — nao fica gravado no crontab.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
MARCA="# autojuri-scrape-jurisprudencia"

if [[ "${1:-}" == "--instalar" ]]; then
	linha_dom="0 6 * * 0 bash $RAIZ/scripts/deploy/scrape_cron.sh >> $HOME/scrape_cron.log 2>&1 $MARCA"
	linha_sem="0 18 * * 1,5 bash $RAIZ/scripts/deploy/scrape_cron.sh >> $HOME/scrape_cron.log 2>&1 $MARCA"
	# Idempotente: remove as linhas antigas desta marca antes de recolocar.
	{ crontab -l 2>/dev/null | grep -vF "$MARCA" || true; echo "$linha_dom"; echo "$linha_sem"; } | crontab -
	echo "[scrape] agendado (UTC): Dom 06h e Seg/Sex 18h = Dom 03h e Seg/Sex 15h em Brasilia."
	crontab -l | grep -F "$MARCA"
	exit 0
fi

TOKEN="$(grep -E '^BACKEND_ADMIN_TOKEN=' "$RAIZ/.env" | head -1 | cut -d= -f2- | tr -d '"\r')"
[[ -n "$TOKEN" ]] || { echo "[scrape] BACKEND_ADMIN_TOKEN ausente em $RAIZ/.env" >&2; exit 1; }

# 202 = coleta agendada em background no backend (~50-80s por fonte).
status="$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
	"http://127.0.0.1:${BACKEND_PORT:-8000}/api/admin/jurisprudencia/scrape" \
	-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
	-d '{"fonte": "todas", "max_por_tema": 4}')"
echo "[scrape] $(date -u +%FT%TZ) HTTP $status"
[[ "$status" == "202" ]]
