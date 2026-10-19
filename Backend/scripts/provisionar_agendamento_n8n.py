"""Provisiona o agendamento de scrape de jurisprudencia no n8n (PR34).

Idempotente. Recupera o setup quando o n8n e recriado do zero (volume
autojuri_n8n_data perdido), quando a credential httpHeaderAuth some, ou pra
subir tudo numa instancia nova:

  1. Cria a credential httpHeaderAuth "AutoJuri Backend Admin (Bearer)" com
     `Authorization: Bearer <BACKEND_ADMIN_TOKEN>` (token cifrado no n8n).
  2. Carrega docs/n8n_workflow_scrape_agendado.json e injeta o id da credential
     no node HTTP Request.
  3. Cria (ou atualiza, se ja existir pelo nome) o workflow e ATIVA.

Roda no HOST (nao no container), com o venv do backend:
    cd Backend
    .venv/Scripts/python.exe scripts/provisionar_agendamento_n8n.py

Le N8N_API_KEY de Backend/.env e BACKEND_ADMIN_TOKEN do .env raiz. O token NAO
vem de process.env no Code node porque o task runner do n8n nao o expoe — por
isso o workflow usa credential (injetada pelo core do n8n). Ver
docs/n8n_workflow_scrape_agendado.json.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
N8N_URL = "http://localhost:5678"
CRED_NAME = "AutoJuri Backend Admin (Bearer)"
WF_NAME = "AutoJuri - Scrape Jurisprudencia Agendado"
WF_JSON = ROOT / "docs" / "n8n_workflow_scrape_agendado.json"


def _le_env(path: Path, chave: str) -> str:
    if not path.exists():
        return ""
    for linha in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if linha.startswith(chave + "="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _api(
    method: str,
    path: str,
    api_key: str,
    body: dict | None = None,
    *,
    tolerante: bool = False,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        N8N_URL + path,
        data=data,
        method=method,
        headers={"X-N8N-API-KEY": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode()[:200]
        if tolerante:  # ex: delete de credential antiga nao deve abortar
            print(f"  (n8n API {method} {path} -> {e.code}: {detalhe})")
            return {}
        raise SystemExit(f"n8n API {method} {path} -> {e.code}: {detalhe}")


def main() -> int:
    api_key = _le_env(ROOT / "Backend" / ".env", "N8N_API_KEY")
    token = _le_env(ROOT / ".env", "BACKEND_ADMIN_TOKEN")
    if not api_key:
        raise SystemExit("N8N_API_KEY ausente em Backend/.env")
    if not token:
        raise SystemExit("BACKEND_ADMIN_TOKEN ausente no .env raiz")
    if not WF_JSON.exists():
        raise SystemExit(f"workflow JSON nao encontrado: {WF_JSON}")

    print(f"n8n={N8N_URL} | token={token[:8]}... | api_key={api_key[:8]}...")

    # 1) acha o workflow existente (por nome) e captura a credential que ele
    #    referencia hoje — pra deletar no fim e nao acumular credentials orfas.
    existentes = _api("GET", "/api/v1/workflows?limit=100", api_key).get("data", [])
    alvo = next((w for w in existentes if w.get("name") == WF_NAME), None)
    cred_antiga = None
    if alvo:
        detalhe = _api("GET", f"/api/v1/workflows/{alvo['id']}", api_key)
        for node in detalhe.get("nodes", []):
            ref = (node.get("credentials") or {}).get("httpHeaderAuth") or {}
            if ref.get("id"):
                cred_antiga = ref["id"]

    # 2) cria a credential nova
    cred = _api(
        "POST",
        "/api/v1/credentials",
        api_key,
        {
            "name": CRED_NAME,
            "type": "httpHeaderAuth",
            "data": {"name": "Authorization", "value": f"Bearer {token}"},
        },
    )
    cred_id = cred["id"]
    print(f"credential criada: id={cred_id}")

    # 3) carrega workflow e injeta a credential nova no node HTTP Request
    wf = json.loads(WF_JSON.read_text(encoding="utf-8"))
    n_http = 0
    for node in wf.get("nodes", []):
        if node.get("type", "").endswith("httpRequest"):
            node["credentials"] = {"httpHeaderAuth": {"id": cred_id, "name": CRED_NAME}}
            n_http += 1
    if n_http == 0:
        raise SystemExit("nenhum node httpRequest no workflow JSON — nada pra vincular")

    payload = {
        "name": wf.get("name", WF_NAME),
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {"executionOrder": "v1"}),
    }

    # 4) cria ou atualiza + ativa
    if alvo:
        wf_id = alvo["id"]
        _api("PUT", f"/api/v1/workflows/{wf_id}", api_key, payload)
        print(f"workflow atualizado: id={wf_id}")
    else:
        criado = _api("POST", "/api/v1/workflows", api_key, payload)
        wf_id = criado["id"]
        print(f"workflow criado: id={wf_id}")

    act = _api("POST", f"/api/v1/workflows/{wf_id}/activate", api_key, {})
    print(f"workflow ativo = {act.get('active')}")

    # 5) remove a credential antiga (agora nao-referenciada) — idempotente
    if cred_antiga and cred_antiga != cred_id:
        _api("DELETE", f"/api/v1/credentials/{cred_antiga}", api_key, tolerante=True)
        print(f"credential antiga removida: id={cred_antiga}")

    print("OK: agendamento provisionado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
