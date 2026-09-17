$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtimePortsPath = Join-Path $Root "backend\storage\runtime-ports.json"

function Test-HttpOk {
  param([string]$Url)
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

if (-not (Test-Path -LiteralPath $runtimePortsPath)) {
  Write-Host "No running port file was found."
  Write-Host "Please run start.bat first, then run open.bat again."
  exit 1
}

$runtime = Get-Content -LiteralPath $runtimePortsPath -Encoding UTF8 | ConvertFrom-Json
$frontendPort = [int]$runtime.frontend_port
if (-not $frontendPort) {
  Write-Host "The running port file does not contain a frontend port."
  Write-Host "Please run start.bat again."
  exit 1
}

$touristUrl = "http://127.0.0.1:$frontendPort"
$adminUrl = "http://127.0.0.1:$frontendPort/admin"

if (-not (Test-HttpOk -Url $touristUrl)) {
  Write-Host "The Lingjing Guide frontend is not responding at $touristUrl."
  Write-Host "Please run start.bat first, then run open.bat again."
  exit 1
}

Write-Host "Opening Tourist app: $touristUrl"
Start-Process $touristUrl
Write-Host "Opening Management center: $adminUrl"
Start-Process $adminUrl
