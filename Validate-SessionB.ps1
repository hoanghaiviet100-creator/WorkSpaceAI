[CmdletBinding()]
param([switch]$ActualModels)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$python=Join-Path $root '.venv-pa2\Scripts\python.exe'
Push-Location $root
try {
  if ($ActualModels) {
    & (Join-Path $root 'Start-SessionB.ps1') -Validation -NoOpen
    $deadline=[DateTime]::UtcNow.AddSeconds(245)
    $ready=$false
    while ([DateTime]::UtcNow -lt $deadline) {
      $state=Invoke-RestMethod -Uri 'http://127.0.0.1:18682/api/runtime/generation-ready' -TimeoutSec 5
      if ($state.ready) { $ready=$true;break }
      if (-not $state.preparing) { throw $state.message }
      Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'The model did not become ready within the bounded preparation period.' }
    $stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    & rtk proxy $python -B tools/run_release_acceptance.py --output (Join-Path $root "validation\release-acceptance-$stamp")
  } else {
    & rtk proxy $python -B tools/check_release.py
  }
  if ($LASTEXITCODE -ne 0) { throw 'Validation reported an error. Read the saved evidence.' }
} finally { Pop-Location }
