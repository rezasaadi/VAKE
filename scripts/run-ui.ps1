param([int]$Port = 8765, [int]$Timeout = 600, [switch]$Open)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = if ($env:VAKE_PYTHON) { $env:VAKE_PYTHON } else { 'python' }
Push-Location $repo
try {
    $arguments = @('-m', 'ui.server', '--port', "$Port", '--timeout', "$Timeout")
    if ($Open) { $arguments += '--open' }
    & $python @arguments
    exit $LASTEXITCODE
} finally { Pop-Location }
