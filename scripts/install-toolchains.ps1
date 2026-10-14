$ErrorActionPreference='Stop'
if(-not (Get-Command rustup -ErrorAction SilentlyContinue)){throw 'Install Rustup first.'}
if(-not (Get-Command elan -ErrorAction SilentlyContinue)){throw 'Install Elan first.'}
& rustup toolchain install 1.97.1 --profile minimal
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& elan toolchain install leanprover/lean4:v4.34.1
exit $LASTEXITCODE
