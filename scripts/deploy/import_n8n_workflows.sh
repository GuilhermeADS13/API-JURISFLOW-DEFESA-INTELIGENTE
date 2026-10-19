#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — importa e PUBLICA (ativa) os 3 workflows de webhook do n8n num
# container ja de pe.
#
# Funciona numa instancia NOVA (sem N8N_API_KEY / sem owner setup): usa a CLI do
# n8n dentro do container (import:workflow + publish:workflow), que escreve direto
# no SQLite, sem precisar de REST/API key. No n8n 2.x "ativar" = publicar; o
# antigo `update:workflow --active` esta depreciado.
#
# O workflow de agendamento (n8n_workflow_scrape_agendado.json) NAO entra aqui:
# ele depende de uma credential httpHeaderAuth que so a API REST cria. Use
# Backend/scripts/provisionar_agendamento_n8n.py para ele.
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

# arquivo:id — o id e o campo "id" do proprio JSON.
WORKFLOWS=(
	n8n_workflow_contestacao_claude.json:WF_AUTOJURI_CONTESTACAO_CLAUDE
	n8n_workflow_contestar_por_peticao.json:WF_AUTOJURI_CONTESTAR_POR_PETICAO
	n8n_workflow_editar_contestacao.json:WF_AUTOJURI_EDITAR_CONTESTACAO
)

echo "[import] container-alvo: $N8N_CONTAINER"
if ! docker ps --format '{{.Names}}' | grep -qx "$N8N_CONTAINER"; then
	echo "[import] ERRO: container $N8N_CONTAINER nao esta rodando. Rode 'docker compose up -d n8n' antes." >&2
	exit 1
fi

echo "[import] importando e publicando ${#WORKFLOWS[@]} workflows..."
for item in "${WORKFLOWS[@]}"; do
	wf="${item%%:*}"
	id="${item##*:}"
	echo "  - $wf ($id)"
	docker exec -u node "$N8N_CONTAINER" \
		n8n import:workflow --input="$WF_DIR_IN_CONTAINER/$wf"
	docker exec -u node "$N8N_CONTAINER" n8n publish:workflow --id="$id"
done

# A CLI escreve no banco; o processo do n8n em execucao so registra os webhooks
# publicados ao (re)iniciar.
echo "[import] reiniciando o n8n para registrar os webhooks..."
docker restart "$N8N_CONTAINER" >/dev/null

for _ in $(seq 1 30); do
	if docker exec "$N8N_CONTAINER" wget -qO- http://localhost:5678/healthz >/dev/null 2>&1; then
		echo "[import] n8n saudavel. Pronto: ${#WORKFLOWS[@]} workflows publicados."
		echo "[import] Agendamento do scrape: rode Backend/scripts/provisionar_agendamento_n8n.py."
		exit 0
	fi
	sleep 2
done
echo "[import] aviso: /healthz nao respondeu em 60s (pode ainda estar subindo)." >&2
