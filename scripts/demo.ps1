param([switch]$Offline)
$ErrorActionPreference='Stop'
$pythonCommand=if($env:VAKE_PYTHON){$env:VAKE_PYTHON}elseif(Get-Command python3 -ErrorAction SilentlyContinue){'python3'}else{'python'}
$arguments=@((Join-Path $PSScriptRoot 'reproduce.py'),'--stage','demo')
if($Offline){$arguments+='--offline'}
& $pythonCommand @arguments
exit $LASTEXITCODE
