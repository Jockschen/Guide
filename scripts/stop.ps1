$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$escapedRoot = [Regex]::Escape($Root)
$runtimePortsPath = Join-Path $Root "backend\storage\runtime-ports.json"

try {
  Get-CimInstance Win32_Process |
    Where-Object {
      ($_.CommandLine -match $escapedRoot) -and
      ($_.CommandLine -match "uvicorn server.main:app" -or $_.CommandLine -match "uvicorn server.opentalking_bridge:app" -or $_.CommandLine -match "apps.unified.main" -or $_.CommandLine -match "prewarm_opentalking.py" -or $_.CommandLine -match "next(\\.cmd)?'? (dev|start)")
    } |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force
    }
} catch {}

if (Test-Path -LiteralPath $runtimePortsPath) {
  $runtime = Get-Content -LiteralPath $runtimePortsPath -Encoding UTF8 | ConvertFrom-Json
  $ports = @(
    $runtime.backend_port,
    $runtime.frontend_port,
    $runtime.opentalking_port,
    $runtime.opentalking_session_port,
    8000,
    8001,
    8011,
    8210,
    3000,
    3001,
    3002
  ) | Where-Object { $_ } | Select-Object -Unique
  foreach ($port in $ports) {
    $pids = netstat -ano |
      Select-String "127.0.0.1:$port\s+.*LISTENING" |
      ForEach-Object { ($_ -split "\s+")[-1] } |
      Where-Object { $_ -match "^\d+$" -and $_ -ne "0" } |
      Select-Object -Unique
    foreach ($pid in $pids) {
      taskkill /PID $pid /T /F | Out-Null
    }
  }
}

Write-Host "Lingjing local services have been asked to stop."
