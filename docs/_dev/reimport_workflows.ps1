# ─────────────────────────────────────────────────────────────────────────────
# Reimporta os workflows n8n no container apos edicao dos JSONs locais.
#
# Fluxo:
#   Para cada workflow:
#     1. Desativa via Public API (PATCH /api/v1/workflows/{id} -> active=false)
#     2. Executa `n8n import:workflow --input=/data/workflows/<file>.json`
#     3. Reativa via Public API (active=true)
#   Depois:
#     4. docker restart autojuri_n8n
#     5. Polling do healthcheck + webhook ate registrar
#
# Pre-requisitos:
#   - Backend/.env com N8N_API_KEY (Public API JWT do owner do n8n)
#   - Container autojuri_n8n rodando
#   - JSONs em /data/workflows/ (montados via docker-compose)
#
# Uso:
#   pwsh docs\_dev\reimport_workflows.ps1
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

function W-Step { param($Msg) Write-Host ">> $Msg" -ForegroundColor Cyan }
function W-Ok   { param($Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function W-Warn { param($Msg) Write-Host "[!!] $Msg" -ForegroundColor Yellow }
function W-Err  { param($Msg) Write-Host "[XX] $Msg" -ForegroundColor Red }

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$EnvFile     = Join-Path $ProjectRoot "Backend\.env"

# ── Carrega N8N_API_KEY do .env ──────────────────────────────────────────────
$N8N_API_KEY = $null
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^N8N_API_KEY=(.+)$') { $N8N_API_KEY = $matches[1].Trim() }
    }
}
if (-not $N8N_API_KEY) {
    W-Err "N8N_API_KEY nao encontrada em $EnvFile"
    exit 1
}
W-Ok "N8N_API_KEY carregada (...$($N8N_API_KEY.Substring($N8N_API_KEY.Length - 8)))"

# ── Mapping workflow_id -> arquivo ───────────────────────────────────────────
$WORKFLOWS = @(
    @{ Id = "WF_AUTOJURI_CONTESTACAO_CLAUDE";        File = "n8n_workflow_contestacao_claude.json" },
    @{ Id = "WF_AUTOJURI_CONTESTAR_POR_PETICAO";     File = "n8n_workflow_contestar_por_peticao.json" },
    @{ Id = "WF_AUTOJURI_EDITAR_CONTESTACAO";        File = "n8n_workflow_editar_contestacao.json" }
)

$N8N_BASE = "http://localhost:5678"
$HEADERS  = @{ "X-N8N-API-KEY" = $N8N_API_KEY; "Accept" = "application/json"; "Content-Type" = "application/json" }

function Toggle-Workflow {
    param([string]$Id, [bool]$Active)
    $action = if ($Active) { "activate" } else { "deactivate" }
    try {
        $r = Invoke-WebRequest -Uri "$N8N_BASE/api/v1/workflows/$Id/$action" -Method POST -Headers $HEADERS -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
        return ($r.StatusCode -in 200, 201)
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        # 400 quando ja esta no estado desejado eh aceitavel
        if ($code -eq 400) { return $true }
        W-Warn "$action($Id) -> HTTP $code"
        return $false
    }
}

# ── 1+2+3. Por workflow: desativar → importar → reativar ─────────────────────
foreach ($wf in $WORKFLOWS) {
    W-Step "[$($wf.Id)] desativando..."
    $null = Toggle-Workflow -Id $wf.Id -Active $false

    W-Step "[$($wf.Id)] importando /data/workflows/$($wf.File)..."
    $out = docker exec autojuri_n8n n8n import:workflow --input=/data/workflows/$($wf.File) 2>&1
    $importOk = ($out -join "`n") -match "Successfully imported"
    if ($importOk) {
        W-Ok "$($wf.Id) imported"
    } else {
        W-Err "$($wf.Id) import falhou. Saida:"
        $out | ForEach-Object { Write-Host "    $_" }
    }

    W-Step "[$($wf.Id)] reativando..."
    $null = Toggle-Workflow -Id $wf.Id -Active $true
}

# ── 4. Restart container para forcar reload completo ─────────────────────────
W-Step "Restart autojuri_n8n para forcar reload..."
docker restart autojuri_n8n | Out-Null

# ── 5. Polling de healthcheck ────────────────────────────────────────────────
W-Step "Aguardando healthcheck..."
$ready = $false
$startTime = Get-Date
while (((Get-Date) - $startTime).TotalSeconds -lt 60) {
    try {
        $r = Invoke-WebRequest -Uri "$N8N_BASE/healthz" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ready) { W-Err "n8n nao ficou healthy em 60s"; exit 1 }
W-Ok "n8n healthy ($([int](((Get-Date)-$startTime).TotalSeconds))s)"

# ── 6. Polling do webhook (precisa NAO retornar 404) ─────────────────────────
W-Step "Aguardando webhook /webhook/contestacao-claude registrar..."
$webhookReady = $false
$startTime = Get-Date
while (((Get-Date) - $startTime).TotalSeconds -lt 30) {
    try {
        $r = Invoke-WebRequest -Uri "$N8N_BASE/webhook/contestacao-claude" -Method POST -Body "{}" -ContentType "application/json" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        # 200 ou 422 (esquema invalido) significa que o webhook esta registrado
        $webhookReady = $true; break
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        if ($code -in 200, 400, 422, 500) { $webhookReady = $true; break }
        # 404 = nao registrado ainda
    }
    Start-Sleep -Seconds 2
}
if (-not $webhookReady) {
    W-Warn "Webhook nao confirmou registro - pode estar caching, prossiga manualmente"
} else {
    W-Ok "Webhook registrado"
}

W-Ok "Reimport concluido. Rode docs\_dev\smoke_test_agente_claude.ps1 para validar."
