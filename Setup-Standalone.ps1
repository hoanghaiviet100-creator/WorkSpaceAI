[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$python=Join-Path $root '.venv-pa2\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  & rtk proxy py -3.12 -m venv (Join-Path $root '.venv-pa2')
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required to create the isolated environment.' }
}
$foreign=Join-Path $root '.venv-pa2\Lib\site-packages\workspace-dependencies.pth'
if (Test-Path -LiteralPath $foreign) { throw 'Remove the legacy shared-dependency .pth before standalone setup.' }
& rtk proxy $python -m pip install -r (Join-Path $root 'requirements-standalone.lock')
if ($LASTEXITCODE -ne 0) { throw 'Pinned standalone dependency installation failed.' }
& rtk proxy $python -B (Join-Path $root 'tools\check_standalone.py')
if ($LASTEXITCODE -ne 0) { throw 'Standalone verification failed.' }
Write-Output 'Standalone dependencies are verified. Existing model artifacts were not downloaded again.'
