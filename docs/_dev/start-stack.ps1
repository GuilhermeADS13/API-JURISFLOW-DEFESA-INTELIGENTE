# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — Inicializa stack para uso com MCP no VSCode/Claude Code.
#
# Faz:
#  1. Verifica se Docker Desktop esta rodando; inicia se necessario
#  2. Aguarda Docker daemon responder
#  3. Sobe containers (backend + n8n) via docker compose
#  4. Aguarda containers ficarem healthy
#  5. Mostra status final com URLs
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File docs\_dev\start-stack.ps1
#   ou duplo-clique em docs\_dev\start-stack.cmd
# ─────────────────────────────────────────────────────────────────────────────

# Native commands (docker, etc) escrevem em stderr coisas inocuas como warnings,
# o que com Stop faria o script abortar. Usamos Continue + checagem de $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

function Write-Status { param($Msg) Write-Host ">> $Msg" -ForegroundColor Cyan }
function Write-Ok     { param($Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Warn   { param($Msg) Write-Host "[!!] $Msg" -ForegroundColor Yellow }
function Write-Err    { param($Msg) Write-Host "[XX] $Msg" -ForegroundColor Red }

# Caminho do projeto: pai do diretorio do script
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot
Write-Status "Projeto: $ProjectRoot"

# ── 1. Garante Docker Desktop iniciado ───────────────────────────────────────
Write-Status "Verificando Docker Desktop..."
$dockerProc = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerProc) {
    Write-Warn "Docker Desktop nao esta aberto. Iniciando..."
    $dockerExe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerExe)) {
        Write-Err "Docker Desktop nao encontrado em $dockerExe"
        exit 1
    }
    Start-Process $dockerExe
    Write-Status "Aguardando Docker Desktop subir (pode demorar 30-60s)..."
} else {
    Write-Ok "Docker Desktop ja esta aberto."
}

# ── 2. Aguarda daemon responder ──────────────────────────────────────────────
$timeout = 90
$elapsed = 0
while ($elapsed -lt $timeout) {
    try {
        docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    } catch {}
    Start-Sleep -Seconds 2
    $elapsed += 2
    Write-Host "." -NoNewline
}
if ($elapsed -ge $timeout) {
    Write-Host ""
    Write-Err "Timeout aguardando Docker daemon ($timeout s)."
    exit 1
}
Write-Host ""
Write-Ok "Docker daemon respondendo."

# ── 3. Sobe containers ───────────────────────────────────────────────────────
Write-Status "Subindo containers via docker compose..."
# Warnings de variaveis nao setadas (.env carregado em runtime) sao inocuos.
$composeOutput = docker compose up -d 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "docker compose up -d falhou."
    $composeOutput | ForEach-Object { Write-Host $_ }
    exit 1
}
$composeOutput | Where-Object { $_ -notmatch "level=warning|DATABASE_URL" } | ForEach-Object {
    Write-Host "  $_" -ForegroundColor DarkGray
}

# ── 4. Aguarda healthy ───────────────────────────────────────────────────────
Write-Status "Aguardando containers ficarem healthy..."
$services = @("autojuri_n8n", "autojuri_backend")
$timeout = 60
$elapsed = 0
$allHealthy = $false
while ($elapsed -lt $timeout) {
    $allHealthy = $true
    foreach ($svc in $services) {
        $status = docker inspect --format "{{.State.Health.Status}}" $svc 2>$null
        if ($status -ne "healthy") {
            $allHealthy = $false
            break
        }
    }
    if ($allHealthy) { break }
    Start-Sleep -Seconds 2
    $elapsed += 2
    Write-Host "." -NoNewline
}
Write-Host ""

if (-not $allHealthy) {
    Write-Warn "Nem todos containers ficaram healthy em $timeout s. Veja docker compose ps."
} else {
    Write-Ok "Todos containers healthy."
}

# ── 5. Status final ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================================" -ForegroundColor DarkGray
$psOutput = docker compose ps --format "table {{.Name}}`t{{.Status}}`t{{.Ports}}" 2>&1
$psOutput | Where-Object { $_ -notmatch "level=warning|DATABASE_URL" } | ForEach-Object {
    Write-Host $_
}
Write-Host "==========================================================" -ForegroundColor DarkGray

# Smoke checks de endpoints
$endpoints = @(
    @{ Name = "Backend (FastAPI)"; Url = "http://localhost:8000/health" }
    @{ Name = "n8n (UI + API)";    Url = "http://localhost:5678/healthz" }
)
foreach ($ep in $endpoints) {
    try {
        $resp = Invoke-WebRequest -Uri $ep.Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Ok "$($ep.Name) -> HTTP $($resp.StatusCode) ($($ep.Url))"
    } catch {
        Write-Warn "$($ep.Name) nao respondeu em $($ep.Url)"
    }
}

Write-Host ""
Write-Ok "Stack pronto. MCPs (MCP_DOCKER + n8n-autojuri) devem reconectar no VSCode automaticamente."
Write-Host ""
Write-Host "Atalhos:" -ForegroundColor DarkGray
Write-Host "  Frontend dev:  cd 'Front end\vite-project' ; npm run dev" -ForegroundColor DarkGray
Write-Host "  Parar stack:   docker compose down" -ForegroundColor DarkGray
Write-Host "  Ver logs:      docker compose logs -f backend" -ForegroundColor DarkGray
