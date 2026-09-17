$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  throw "未找到 .venv，请先运行 start.bat。"
}
$env:PYTHONPATH = Join-Path $Root "backend"
& $Python -m server.cli rebuild
