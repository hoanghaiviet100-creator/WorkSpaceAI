[CmdletBinding()]
param([switch]$Validation, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv-pa2\Scripts\python.exe'
$node = 'D:\WorkspaceAI-F1-Toolchain\node-v22.23.5-win-x64\node.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Existing Python runtime is unavailable.' }
& rtk proxy $python -B (Join-Path $root 'tools\check_standalone.py') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Standalone dependencies are not verified. Run Setup-Standalone.ps1.' }
$runtime = Join-Path $root $(if ($Validation) { '.runtime-validation' } else { '.runtime-app' })
$port = if ($Validation) { 18682 } else { 18681 }
New-Item -ItemType Directory -Force -Path $runtime,(Join-Path $root '.runtime\ollama-home'),(Join-Path $root '.runtime\models') | Out-Null
$pidFile = Join-Path $runtime 'process.json'
if (Test-Path -LiteralPath $pidFile) {
  $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
  $existing = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
  if ($existing -and $existing.StartTime.ToUniversalTime().ToString('o') -eq $record.started) {
    Write-Output "Session B is already running at http://127.0.0.1:$port"; return
  }
}
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already occupied. No existing process was changed." }
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\dist\index.html'))) {
  Push-Location (Join-Path $root 'frontend')
  try {
    & rtk proxy $node 'node_modules/typescript/bin/tsc' -b
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript compilation failed.' }
    & rtk proxy $node 'node_modules/vite/bin/vite.js' build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
  } finally { Pop-Location }
}
& rtk proxy $python -B (Join-Path $root 'tools\prepare_adaptive_models.py') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Approved local model preparation failed.' }
$env:F1_PROMPT_CACHE_MIB = (& rtk proxy $python -B (Join-Path $root 'tools\runtime_cache.py')).Trim()
if ($LASTEXITCODE -ne 0 -or $env:F1_PROMPT_CACHE_MIB -ne '512') { throw 'Could not calculate bounded prompt cache.' }
& rtk proxy docker compose -p workspaceai-f1-session-b -f (Join-Path $root 'compose.session-b.yml') -f (Join-Path $root 'compose.models-readonly.yml') up -d --pull never
if ($LASTEXITCODE -ne 0) { throw 'Could not start the isolated Session B Ollama service.' }
$modelReady=$false
for ($attempt=0; $attempt -lt 30; $attempt++) {
  try {
    $inventory=Invoke-RestMethod -Uri 'http://127.0.0.1:18684/api/tags' -TimeoutSec 2
    $names=@($inventory.models | ForEach-Object { $_.name })
    if ('qwen2.5:7b-q4_K_M' -notin $names) { throw 'Required installed models are missing.' }
    $modelReady=$true; break
  } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $modelReady) { throw 'The isolated model service is not ready. Check Session B Docker logs; no model download was attempted.' }
& rtk proxy $python -B (Join-Path $root 'tools\cache_adaptive_metadata.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect installed model metadata.' }
$env:F1_SESSION_B='true'
$env:F1_GENERATION_PRELOAD='true'
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:LLM_PROVIDER='ollama'
$env:OLLAMA_BASE_URL='http://127.0.0.1:18684'
$env:F1_GENERATION_MODEL='qwen2.5:7b-q4_K_M'
$env:F1_MODEL_DIGEST='156bcbf71df68f7a6581fb4ab306ed921b8114d82b6eaeab5c0442785ea9b4c3'
$env:F1_EMBEDDING_BACKEND='fastembed_cpu'
$env:F1_CPU_ENCODER=Join-Path $root '.runtime\cpu-embedding\qwen3-0.6b-int8\encoder.json'
if (-not (Test-Path -LiteralPath $env:F1_CPU_ENCODER)) { throw 'Prepare the pinned CPU encoder before starting.' }
$env:F1_GENERATION_THINK='false'
$env:OLLAMA_EMBED_MODEL='qwen3-embedding:0.6b'
$env:F1_RUNTIME_DIR=$runtime
$env:F1_STORE_PATH=Join-Path $runtime 'library.json'
$env:F1_ADAPTIVE_POLICY=Join-Path $root '.runtime\cpu-generation-policy.json'
$env:F1_NLI_WARMUP='false'
$env:SQLITE_DB_PATH=Join-Path $runtime 'workspace.db'
$env:EMAIL_DISPATCH_MODE='local_mock'
$env:GEMINI_API_KEY=''
$env:GMAIL_APP_PASSWORD=''
$process = Start-Process -FilePath $python -ArgumentList @('-B','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',"$port") -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'app.stdout.log') -RedirectStandardError (Join-Path $runtime 'app.stderr.log')
@{ pid=$process.Id; started=$process.StartTime.ToUniversalTime().ToString('o'); port=$port; root=$root } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8
$ready=$false
for ($attempt=0; $attempt -lt 40; $attempt++) {
  try { $null=Invoke-RestMethod -Uri "http://127.0.0.1:$port/openapi.json" -TimeoutSec 2; $ready=$true; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ready) { throw "Session B did not become ready. Read $runtime\app.stderr.log" }
Write-Output "WorkspaceAI is open at http://127.0.0.1:$port. The AI model is getting ready; documents can be uploaded while waiting."
if (-not $NoOpen) { Start-Process "http://127.0.0.1:$port" }
