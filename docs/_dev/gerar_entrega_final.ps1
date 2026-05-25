# ─────────────────────────────────────────────────────────────────────────────
# Gera o documento ENTREGA_FINAL completo: screenshots + PDF.
#
# Fluxo:
#  1. Confere se stack (backend, n8n, frontend Vite) esta de pe
#  2. Garante node_modules de docs/_dev/ instalados
#  3. Captura os 6 screenshots via Playwright
#  4. Compila o PDF via gerar_pdf_entrega_final.py
#  5. Valida paginas (8-12) e tamanho do PDF
#
# Uso:
#   pwsh docs\_dev\gerar_entrega_final.ps1
#   pwsh docs\_dev\gerar_entrega_final.ps1 -SkipScreenshots
#     (regenera so o PDF, mantem os PNGs atuais)
# ─────────────────────────────────────────────────────────────────────────────

param(
    [switch]$SkipScreenshots
)

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

function Write-Step { param($Msg) Write-Host ">> $Msg" -ForegroundColor Cyan }
function Write-Ok   { param($Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Err  { param($Msg) Write-Host "[XX] $Msg" -ForegroundColor Red }

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot
Write-Step "Projeto: $ProjectRoot"

$DevDir   = Join-Path $ProjectRoot "docs\_dev"
$PyVenv   = Join-Path $ProjectRoot "Backend\.venv\Scripts\python.exe"
$PdfPath  = Join-Path $ProjectRoot "docs\ENTREGA_FINAL.pdf"

# ── 1. Smoke check ───────────────────────────────────────────────────────────
if (-not $SkipScreenshots) {
    Write-Step "Conferindo stack (backend, n8n, vite)..."
    $endpoints = @(
        "http://localhost:5173/",
        "http://localhost:8000/health",
        "http://localhost:5678/healthz"
    )
    $stackUp = $true
    foreach ($u in $endpoints) {
        try {
            $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 4
            if ($r.StatusCode -ne 200) { $stackUp = $false }
        } catch { $stackUp = $false; Write-Err "$u DOWN" }
    }
    if (-not $stackUp) {
        Write-Err "Stack incompleta. Suba antes:"
        Write-Host "  pwsh docs\_dev\start-stack.ps1"
        Write-Host "  cd 'Front end\vite-project'; npm run dev"
        exit 1
    }
    Write-Ok "Stack OK"

    # ── 2. node_modules ──────────────────────────────────────────────────────
    $nodeModules = Join-Path $DevDir "node_modules"
    if (-not (Test-Path $nodeModules)) {
        Write-Step "Instalando dependencias (playwright)..."
        Push-Location $DevDir
        npm install --silent
        if ($LASTEXITCODE -ne 0) { Write-Err "npm install falhou"; exit 1 }
        npx --yes playwright install chromium
        Pop-Location
    }
    Write-Ok "Playwright pronto"

    # ── 3. Capturar screenshots ─────────────────────────────────────────────
    Write-Step "Capturando 6 screenshots..."
    Push-Location $DevDir
    node capturar_screenshots.mjs
    if ($LASTEXITCODE -ne 0) { Write-Err "Captura falhou"; Pop-Location; exit 1 }
    Pop-Location
    Write-Ok "Screenshots gerados"
}

# ── 4. Gerar PDF ────────────────────────────────────────────────────────────
Write-Step "Compilando ENTREGA_FINAL.pdf..."
& $PyVenv (Join-Path $ProjectRoot "docs\gerar_pdf_entrega_final.py")
if ($LASTEXITCODE -ne 0) { Write-Err "Geracao do PDF falhou"; exit 1 }

# ── 5. Validar ──────────────────────────────────────────────────────────────
Write-Step "Validando PDF..."
$validacao = & $PyVenv -c @"
from pypdf import PdfReader
import os, sys
p = r'$PdfPath'
if not os.path.exists(p):
    print('MISSING'); sys.exit(1)
r = PdfReader(p)
n = len(r.pages)
sz = os.path.getsize(p) / 1024
ok = (8 <= n <= 12) and (200 <= sz <= 6000)
print(f'PAGES={n} SIZE_KB={sz:.0f} OK={ok}')
sys.exit(0 if ok else 2)
"@
Write-Host $validacao
if ($LASTEXITCODE -ne 0) {
    Write-Err "Validacao falhou (paginas fora de 8-12 ou tamanho fora de 0.2-6 MB)"
    exit 1
}
Write-Ok "Documento pronto: $PdfPath"
