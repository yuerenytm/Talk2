$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
& $python (Join-Path $PSScriptRoot "build.py")
exit $LASTEXITCODE
