#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — importa e ATIVA os 4 workflows do n8n num container ja de pe.
#
# Funciona numa instancia NOVA (sem N8N_API_KEY / sem owner setup): usa a CLI do
# n8n dentro do container (import:workflow + update:workflow), que escreve direto
# no SQLite, sem precisar de REST/API key.
#
# O compose ja monta ./docs:/data/workflows:ro, entao os JSONs aparecem em
# /data/workflows/ dentro do container.
#
# Uso (a partir da raiz do repo, com os containers rodando):
#   bash scripts/deploy/import_n8n_workflows.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

N8N_CONTAINER="${N8N_CONTAINER:-autojuri_n8n}"
WF_DIR_IN_CONTAINER="/data/workflows"

WORKFLOWS=(
	n8n_workflow_contestacao_claude.json
	n8n_workflow_contestar_por_peticao.json
	n8n_workflow_editar_contestacao.json
	n8n_workflow_scrape_agendado.json
)

echo "[import] container-alvo: $N8N_CONTAINER"
if ! docker ps --format '{{.Names}}' | grep -qx "$N8N_CONTAINER"; then
	echo "[import] ERRO: container $N8N_CONTAINER nao esta rodando. Rode 'docker compose up -d n8n' antes." >&2
	exit 1
fi

echo "[import] importando ${#WORKFLOWS[@]} workflows..."
for wf in "${WORKFLOWS[@]}"; do
	echo "  - $wf"
	docker exec -u node "$N8N_CONTAINER" \
		n8n import:workflow --input="$WF_DIR_IN_CONTAINER/$wf"
done

echo "[import] ativando todos os workflows (registra webhooks + schedule)..."
# import:workflow importa DESATIVADO; ativa tudo de uma vez (CLI, sem API key).
docker exec -u node "$N8N_CONTAINER" n8n update:workflow --all --active=true

echo "[import] OK. Conferindo /healthz do n8n..."
docker exec "$N8N_CONTAINER" wget -qO- http://localhost:5678/healthz >/dev/null 2>&1 \
	&& echo "[import] n8n saudavel." \
	|| echo "[import] aviso: /healthz nao respondeu (pode ainda estar subindo)."

echo "[import] Pronto. Os 4 workflows estao importados e ativos."
