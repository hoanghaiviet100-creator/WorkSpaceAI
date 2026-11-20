$ErrorActionPreference = 'Stop'

$sourceRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'vendor/surfsense'
$sourceCommit = 'b764f2838969974fd1b0e8c386326039a0f3ad3a'

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    git clone --depth 1 --branch v2.3.1 --config core.longpaths=true https://github.com/MODSetter/SurfSense.git $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not clone SurfSense.' }
}

$sourceHead = git -C $sourceRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $sourceHead -ne $sourceCommit) {
    throw "SurfSense source must be at $sourceCommit. Check $sourceRoot before building."
}
Write-Output $sourceRoot
