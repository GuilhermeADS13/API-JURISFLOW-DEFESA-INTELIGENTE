#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — boot do CONTAINER UNICO no Hugging Face Spaces (Docker SDK).
#
# O storage do HF Spaces free e EFEMERO: o SQLite do n8n em $N8N_USER_FOLDER
# some a cada restart do Space. Por isso, a cada boot este script:
#   1) re-importa os workflows do repo (escreve direto no SQLite, sem REST/owner)
#   2) ativa todos (registra os webhooks quando o n8n subir)
#   3) sobe o n8n interno (:5678) em background
#   4) sobe o backend FastAPI publico (:7860, a UNICA porta que o HF expoe)
#
# EXPERIMENTAL: nao foi validado end-to-end (nao ha ambiente HF aqui). O caminho
# testado/recomendado e o VPS — ver docs/deploy_backend.md.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

export N8N_USER_FOLDER="${N8N_USER_FOLDER:-/app/.n8n}"
mkdir -p "$N8N_USER_FOLDER"

echo "[hf] (1/4) importando workflows do repo (storage efemero)..."
# import:workflow escreve direto no SQLite — nao precisa de owner/API key.
# --separate = um arquivo .json por workflow no diretorio.
if ! n8n import:workflow --separate --input=/app/workflows; then
	echo "[hf] aviso: import falhou (formato do JSON pode nao ser o de export do n8n;"
	echo "[hf]        alternativa: importar 1x pela UI e re-exportar em formato CLI)."
fi

echo "[hf] (2/4) ativando workflows (registra os webhooks)..."
n8n update:workflow --all --active=true || echo "[hf] aviso: nao consegui ativar via CLI."

echo "[hf] (3/4) subindo n8n interno (:5678)..."
n8n start &
N8N_PID=$!

echo "[hf] aguardando n8n /healthz (ate ~120s)..."
for _ in $(seq 1 60); do
	if curl -sf http://localhost:5678/healthz >/dev/null 2>&1; then
		echo "[hf] n8n pronto."
		break
	fi
	# se o n8n morreu, nao adianta esperar
	if ! kill -0 "$N8N_PID" 2>/dev/null; then
		echo "[hf] ERRO: processo do n8n encerrou durante o boot." >&2
		break
	fi
	sleep 2
done

echo "[hf] (4/4) subindo backend FastAPI (publico :7860)..."
# exec: o uvicorn vira o processo 1; se cair, o container reinicia (HF cuida disso).
exec uvicorn main:app --host 0.0.0.0 --port 7860
