param([ValidateSet('auto','offline','gemini','ollama')][string]$Engine = 'auto')
$ErrorActionPreference = 'Stop'
$workspaceRoot = $PSScriptRoot
$frontendRoot = Join-Path $workspaceRoot 'frontend'
$runtimeRoot = Join-Path $workspaceRoot '.workspace_data\runtime'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

function Test-LocalPort([int]$Port) {
    $socket = New-Object System.Net.Sockets.TcpClient
    try { $connection = $socket.ConnectAsync('127.0.0.1', $Port); return ($connection.Wait(800) -and $socket.Connected) }
    catch { return $false }
    finally { $socket.Dispose() }
}
function Wait-LocalService([string]$Url, [int]$Attempts = 30) {
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        try { $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2; if ($response.StatusCode -eq 200) { return } }
        catch { Start-Sleep -Milliseconds 400 }
    }
    throw "Service did not become ready: $Url. Check logs in $runtimeRoot."
}

$pythonOptions = @(
    (Join-Path $workspaceRoot '.venv\Scripts\python.exe'),
    (Join-Path (Split-Path $workspaceRoot -Parent) '.venv-schema-audit\Scripts\python.exe')
)
$workspacePython = $null
foreach ($option in $pythonOptions) {
    if (Test-Path -LiteralPath $option) {
        & $option -c 'import fastapi, uvicorn, pypdf, rank_bm25, httpx' 2>$null
        if ($LASTEXITCODE -eq 0) { $workspacePython = $option; break }
    }
}
if (-not $workspacePython) {
    $systemPython = (Get-Command python -ErrorAction Stop).Source
    & $systemPython -c 'import fastapi, uvicorn, pypdf, rank_bm25, httpx' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Install backend dependencies with: python -m pip install -r requirements.txt' }
    $workspacePython = $systemPython
}
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodeExecutable = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' }
if (-not (Test-Path -LiteralPath $nodeExecutable)) { throw 'Install Node.js 22 or newer before starting the frontend.' }
$viteEntry = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $viteEntry)) { throw 'Install frontend dependencies with: cd frontend; pnpm install --frozen-lockfile' }

Push-Location $workspaceRoot
try {
    # Load the local dotenv in the child runtime; never print or put a key in command arguments.
    $providerProbe = & $workspacePython -c "import json; from backend.core.config import settings; from backend.providers.llm_provider import llm_provider; print(json.dumps({'provider':settings.llm_provider,'gemini':llm_provider.is_gemini_configured(),'offline_only':settings.offline_only}))"
    $configuredProvider = $providerProbe | ConvertFrom-Json
    if ($Engine -eq 'auto') {
        if ($configuredProvider.offline_only) { $Engine = 'offline' }
        elseif ($configuredProvider.gemini) { $Engine = 'gemini' }
        elseif ($configuredProvider.provider -eq 'ollama') { $Engine = 'ollama' }
        else { $Engine = 'offline' }
    }
    $env:LLM_PROVIDER = if ($Engine -eq 'offline') { 'mock' } else { $Engine }
    $env:WORKSPACE_OFFLINE_ONLY = if ($Engine -eq 'offline') { 'true' } else { 'false' }
    if ($Engine -eq 'offline') { $env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1' }
    $env:EMAIL_DISPATCH_MODE = 'local_mock'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUNBUFFERED = '1'
    $env:VITE_API_ENABLED = 'true'
    $env:VITE_API_BASE_URL = '/api'

    if (-not (Test-LocalPort 8000)) {
        $backendProcess = Start-Process -FilePath $workspacePython -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $workspaceRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'backend.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'backend.err.log') -PassThru
        $backendProcess.Id | Set-Content -LiteralPath (Join-Path $runtimeRoot 'backend.pid')
    }
    Wait-LocalService 'http://127.0.0.1:8000/api/runtime'
    $runtimeStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/runtime' -TimeoutSec 3
    if (-not $runtimeStatus.engine_mode) { throw 'Port 8000 is in use by another service. WorkspaceAI was not started.' }
    if ($Engine -eq 'offline' -and -not $runtimeStatus.offline_only) { throw 'The existing backend has not applied offline-only mode. Restart the WorkspaceAI backend before continuing.' }

    if (-not (Test-LocalPort 5174)) {
        $frontendProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @(('"' + $viteEntry + '"'),'--host','127.0.0.1','--port','5174','--strictPort') -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend.err.log') -PassThru
        $frontendProcess.Id | Set-Content -LiteralPath (Join-Path $runtimeRoot 'frontend.pid')
    }
    Wait-LocalService 'http://127.0.0.1:5174/'
    $frontendResponse = Invoke-WebRequest -Uri 'http://127.0.0.1:5174/' -UseBasicParsing -TimeoutSec 3
    if ($frontendResponse.Content -notmatch 'WorkspaceAI') { throw 'Port 5174 belongs to another application.' }
    Write-Output 'WorkspaceAI is ready: http://127.0.0.1:5174/#workspace/midterm/chat/midterm-deadline'
    Write-Output ('Engine: ' + $runtimeStatus.engine_mode)
    if ($runtimeStatus.offline_only) { Write-Output 'Offline document lookup is active. Cloud AI requests are disabled; no API key is needed.' }
    elseif (-not $runtimeStatus.gemini_configured) { Write-Output 'Select Set up Gemini in the chat composer to add your API key on this device.' }
    Write-Output ('Logs: ' + $runtimeRoot)
}
finally { Pop-Location }
