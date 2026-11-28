[CmdletBinding()]
param([switch]$Validation,[switch]$StopModels)
$ErrorActionPreference='Stop'
$runtime=Join-Path $PSScriptRoot $(if($Validation){'.runtime-validation'}else{'.runtime-app'})
$pidFile=Join-Path $runtime 'process.json'
if(Test-Path -LiteralPath $pidFile){
  $record=Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
  $owned=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
  if($owned -and $owned.StartTime.ToUniversalTime().ToString('o') -eq $record.started){ Stop-Process -Id $owned.Id }
  Remove-Item -LiteralPath $pidFile
}
if($StopModels){
  & rtk proxy docker compose -p workspaceai-f1-session-b -f (Join-Path $PSScriptRoot 'compose.session-b.yml') -f (Join-Path $PSScriptRoot 'compose.models-readonly.yml') down
  if($LASTEXITCODE -ne 0){throw 'Session B container shutdown failed.'}
}
