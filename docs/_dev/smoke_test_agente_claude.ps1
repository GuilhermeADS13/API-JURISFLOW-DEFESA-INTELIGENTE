# ─────────────────────────────────────────────────────────────────────────────
# Smoke test E2E do agente Claude (workflow contestacao-claude).
#
# Dispara o webhook real com payload de caso ficticio e valida 6 assercoes
# baseadas na ESTRUTURA REAL de saida do workflow (apos node "Montar Minuta"
# que reorganiza a resposta):
#
#   1. engine_ia.provider == "claude"             (API respondeu, sem fallback)
#   2. engine_ia.endpoint contem /v1/messages     (BUG 2 fixado: template limpo)
#   3. engine_ia.api_error == null                (sem SyntaxError do BUG 5)
#   4. minuta._campos_incompletos ausente         (BUG 1 fixado)
#   5. minuta.secoes.sintese tem conteudo         (geracao OK + sem '[' inicial)
#   6. minuta.secoes.fundamentos > 1000 chars     (peça com substancia)
#
# Uso:
#   pwsh docs\_dev\smoke_test_agente_claude.ps1
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

function W-Step { param($Msg) Write-Host ">> $Msg" -ForegroundColor Cyan }
function W-Ok   { param($Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function W-Fail { param($Msg) Write-Host "[XX] $Msg" -ForegroundColor Red }
function W-Info { param($Msg) Write-Host "     $Msg" -ForegroundColor DarkGray }

# ── Payload de teste (caso trabalhista ficticio) ─────────────────────────────
$payload = @{
    numero_processo  = "0001234-56.2026.5.06.0100"
    autor            = "Joao da Silva"
    reu              = "Empresa Demo Ltda"
    tipo_acao        = "Trabalhista"
    fatos            = "O reclamante foi admitido em 01/01/2020 como assistente administrativo, com salario mensal de R$ 2.500,00. Foi dispensado sem justa causa em 15/03/2026, tendo trabalhado em sobrejornada habitual sem recebimento das horas extras correspondentes."
    pedido_autor     = "Pagamento das horas extras laboradas e nao quitadas, reflexos nas demais verbas trabalhistas, condenacao em honorarios sucumbenciais."
    pontos_usuario   = @(
        "Ausencia de prova documental das horas extras alegadas",
        "Compensacao de jornada via banco de horas formalizado",
        "Adicional ja incluido em verbas pagas"
    )
    arquivo_base     = @{ conteudo_texto = "" }
    modelo_mae_texto = ""
} | ConvertTo-Json -Compress -Depth 10

W-Step "Disparando webhook contestacao-claude com payload de teste..."
W-Info "URL: http://localhost:5678/webhook/contestacao-claude"
W-Info "Caso: $(($payload | ConvertFrom-Json).numero_processo) | $(($payload | ConvertFrom-Json).tipo_acao)"

$startTime = Get-Date
try {
    $r = Invoke-WebRequest -Uri "http://localhost:5678/webhook/contestacao-claude" `
                            -Method POST -Body $payload `
                            -ContentType "application/json" `
                            -UseBasicParsing -TimeoutSec 180 -ErrorAction Stop
} catch {
    W-Fail "Webhook falhou: $($_.Exception.Message.Split([char]10)[0])"
    exit 1
}
$elapsed = [int]((Get-Date) - $startTime).TotalSeconds

if ($r.StatusCode -ne 200) {
    W-Fail "HTTP $($r.StatusCode) (esperado 200)"; exit 1
}
W-Ok "HTTP 200 | resposta: $($r.Content.Length) bytes | tempo: ${elapsed}s"

try { $resp = $r.Content | ConvertFrom-Json }
catch { W-Fail "Resposta nao eh JSON valido"; exit 1 }

# ── 6 assercoes (baseadas em estrutura real pos node "Montar Minuta") ─────────
$failures = @()
W-Step "Validando 6 assercoes..."

# 1. provider == claude
if ($resp.engine_ia.provider -eq "claude") {
    W-Ok "  [1] engine_ia.provider == 'claude'"
} else {
    $failures += "provider = '$($resp.engine_ia.provider)'"
    W-Fail "  [1] engine_ia.provider == '$($resp.engine_ia.provider)'"
}

# 2. endpoint clean
$endpoint = $resp.engine_ia.endpoint
if ($endpoint -eq "https://api.anthropic.com/v1/messages") {
    W-Ok "  [2] engine_ia.endpoint limpo (BUG 2 fixado)"
} else {
    $failures += "endpoint = '$endpoint'"
    W-Fail "  [2] endpoint = '$endpoint'"
}

# 3. api_error == null (sem SyntaxError / sem fallback)
if ($null -eq $resp.engine_ia.api_error) {
    W-Ok "  [3] engine_ia.api_error == null (sem SyntaxError do BUG 5)"
} else {
    $failures += "api_error = '$($resp.engine_ia.api_error)'"
    W-Fail "  [3] api_error = '$($resp.engine_ia.api_error)'"
}

# 4. _campos_incompletos ausente/vazio (BUG 1)
$camposIncomp = $resp.minuta._campos_incompletos
if (-not $camposIncomp -or @($camposIncomp).Count -eq 0) {
    W-Ok "  [4] minuta._campos_incompletos ausente (BUG 1 fixado)"
} else {
    $failures += "_campos_incompletos = $($camposIncomp -join ', ')"
    W-Fail "  [4] _campos_incompletos = $($camposIncomp -join ', ')"
}

# 5. secoes.sintese tem conteudo
$sintese = $resp.minuta.secoes.sintese
if ($sintese -and $sintese.Length -gt 100 -and -not $sintese.StartsWith("[")) {
    W-Ok "  [5] minuta.secoes.sintese = $($sintese.Length) chars (peca abertura presente)"
} else {
    $failures += "sintese len=$($sintese.Length)"
    W-Fail "  [5] sintese len=$($sintese.Length) | inicio: '$($sintese.Substring(0, [Math]::Min(50, $sintese.Length)))'"
}

# 6. fundamentos com substancia (>1000 chars)
$fundamentos = $resp.minuta.secoes.fundamentos
if ($fundamentos -and $fundamentos.Length -gt 1000) {
    W-Ok "  [6] minuta.secoes.fundamentos = $($fundamentos.Length) chars (peca substancial)"
} else {
    $failures += "fundamentos len=$($fundamentos.Length)"
    W-Fail "  [6] fundamentos len=$($fundamentos.Length)"
}

# ── Resumo final ─────────────────────────────────────────────────────────────
Write-Host ""
W-Step "═══════════════════════════════════════════════════════════════"
W-Step "Resumo da execucao"
W-Info "  provider:           $($resp.engine_ia.provider)"
W-Info "  model:              $($resp.engine_ia.model)"
W-Info "  endpoint:           $($resp.engine_ia.endpoint)"
W-Info "  temperature:        $($resp.engine_ia.temperature)"
W-Info "  max_tokens:         $($resp.engine_ia.max_tokens)"
W-Info "  api_error:          $($resp.engine_ia.api_error)"
W-Info "  resposta_total:     $($r.Content.Length) bytes"
W-Info "  tempo_total:        ${elapsed}s"
W-Info ""
W-Info "  minuta.secoes.sintese:      $($resp.minuta.secoes.sintese.Length) chars"
W-Info "  minuta.secoes.fundamentos:  $($resp.minuta.secoes.fundamentos.Length) chars"
W-Info "  minuta.secoes.pedidos:      $($resp.minuta.secoes.pedidos.Length) chars"
W-Info "  minuta.texto_base:          $($resp.minuta.texto_base.Length) chars"
W-Info "  minuta.tese_central:        $($resp.minuta.tese_central.Length) chars"
W-Info "  minuta.resumo_estrategico:  $($resp.minuta.resumo_estrategico.Length) chars"
W-Info "  minuta.pontos_atendidos:    $(@($resp.minuta.pontos_atendidos).Count) itens"
W-Info "  minuta.riscos:              $(@($resp.minuta.riscos).Count) itens"
W-Step "═══════════════════════════════════════════════════════════════"

if ($failures.Count -eq 0) {
    Write-Host ""
    W-Ok "TODOS OS 6 TESTES PASSARAM"
    Write-Host ""
    W-Info "Voce pode agora abrir http://localhost:5173 e testar manualmente."
    exit 0
} else {
    Write-Host ""
    W-Fail "$($failures.Count) ASSERCAO(OES) FALHARAM:"
    $failures | ForEach-Object { W-Info "  - $_" }
    exit 1
}
