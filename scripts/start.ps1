param(
  [string]$PythonPath = $env:LINGJING_PYTHON,
  [switch]$KeepAlive,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$stopScript = Join-Path $Root "scripts\stop.ps1"
if (Test-Path -LiteralPath $stopScript) {
  powershell -NoProfile -ExecutionPolicy Bypass -File $stopScript | Out-Null
}

function Resolve-CommandPath($Name) {
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Test-PortAvailable {
  param([int]$Port)
  $listener = $null
  try {
    $address = [System.Net.IPAddress]::Parse("127.0.0.1")
    $listener = [System.Net.Sockets.TcpListener]::new($address, $Port)
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    if ($listener) { $listener.Stop() }
  }
}

function Resolve-FreePort {
  param([int]$Preferred)
  for ($port = $Preferred; $port -lt ($Preferred + 30); $port++) {
    if (Test-PortAvailable -Port $port) { return $port }
  }
  throw "No local port is available near 3000 or 8000. Close the program using those ports and try again."
}

function Get-DotEnvValue {
  param([string]$Name)
  $envPath = Join-Path $Root ".env"
  if (-not (Test-Path -LiteralPath $envPath)) { return "" }
  foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
    $parts = $trimmed.Split("=", 2)
    if ($parts[0].Trim() -eq $Name) {
      return $parts[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

function Resolve-PortFromUrl {
  param([string]$Url, [int]$DefaultPort)
  try {
    $uri = [System.Uri]::new($Url)
    if ($uri.Port -gt 0) { return $uri.Port }
  } catch {}
  return $DefaultPort
}

function Start-HiddenProcess {
  param([string]$FilePath, [string]$Arguments)
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $FilePath
  $psi.Arguments = $Arguments
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $true
  $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  [System.Diagnostics.Process]::Start($psi) | Out-Null
}

function ConvertTo-PowerShellLiteral {
  param([AllowNull()][string]$Value)
  if ($null -eq $Value) { return "''" }
  return "'" + ($Value -replace "'", "''") + "'"
}

function Start-HiddenService {
  param(
    [string]$Name,
    [string]$FilePath,
    [string[]]$Arguments,
    [hashtable]$Environment = @{}
  )
  $runtimeDir = Join-Path $Root "backend\storage"
  $logDir = Join-Path $runtimeDir "logs"
  $scriptDir = Join-Path $runtimeDir "runtime-scripts"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  New-Item -ItemType Directory -Force -Path $scriptDir | Out-Null
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $latestPath = Join-Path $logDir "$Name.latest.log"
  $commandPath = Join-Path $logDir "$Name-$stamp.command.txt"
  $outPath = Join-Path $logDir "$Name-$stamp.out.log"
  $errPath = Join-Path $logDir "$Name-$stamp.err.log"
  $exitPath = Join-Path $logDir "$Name-$stamp.exit.log"
  $launcherPath = Join-Path $scriptDir "$Name-$stamp.ps1"
  $argumentText = ($Arguments | ForEach-Object { ConvertTo-PowerShellLiteral $_ }) -join ", "
  $envLines = @()
  foreach ($key in ($Environment.Keys | Sort-Object)) {
    $envLines += ("`$env:{0} = {1}" -f $key, (ConvertTo-PowerShellLiteral ([string]$Environment[$key])))
  }
  $launcher = @(
    '$ErrorActionPreference = "Continue"',
    "Set-Location -LiteralPath $(ConvertTo-PowerShellLiteral $Root)",
    "`$exe = $(ConvertTo-PowerShellLiteral $FilePath)",
    "`$arguments = @($argumentText)",
    "`$outPath = $(ConvertTo-PowerShellLiteral $outPath)",
    "`$errPath = $(ConvertTo-PowerShellLiteral $errPath)",
    "`$exitPath = $(ConvertTo-PowerShellLiteral $exitPath)",
    'Remove-Item -LiteralPath $outPath,$errPath,$exitPath -Force -ErrorAction SilentlyContinue'
  ) + $envLines + @(
    '"started=" + (Get-Date -Format "o") | Set-Content -LiteralPath $exitPath -Encoding UTF8',
    '& $exe @arguments 1>> $outPath 2>> $errPath',
    '$code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }',
    '"exit_code=" + $code | Add-Content -LiteralPath $exitPath -Encoding UTF8',
    '"stopped=" + (Get-Date -Format "o") | Add-Content -LiteralPath $exitPath -Encoding UTF8',
    'exit $code'
  )
  Set-Content -LiteralPath $launcherPath -Value $launcher -Encoding UTF8
  Set-Content -LiteralPath $commandPath -Value @(
    "file=$FilePath",
    "args=$($Arguments -join ' ')",
    "launcher=$launcherPath",
    "stdout=$outPath",
    "stderr=$errPath",
    "exit=$exitPath"
  ) -Encoding UTF8
  Set-Content -LiteralPath $latestPath -Value @(
    "command=$commandPath",
    "launcher=$launcherPath",
    "stdout=$outPath",
    "stderr=$errPath",
    "exit=$exitPath"
  ) -Encoding UTF8
  $powershellExe = Resolve-CommandPath "powershell"
  if (-not $powershellExe) { $powershellExe = "powershell.exe" }
  Start-HiddenProcess -FilePath $powershellExe -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`""
}

function Wait-HttpOk {
  param([string]$Url, [int]$TimeoutSeconds = 45)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    } catch {}
    Start-Sleep -Milliseconds 700
  }
  return $false
}

function Clear-NextBuild {
  $target = Resolve-Path -LiteralPath (Join-Path $Root ".next") -ErrorAction SilentlyContinue
  if ($target -and $target.Path.StartsWith($Root)) {
    Remove-Item -LiteralPath $target.Path -Recurse -Force
  }
}

function Resolve-Python {
  param([string]$Preferred)
  if ($Preferred -and (Test-Path -LiteralPath $Preferred)) {
    return @{ Exe = (Resolve-Path -LiteralPath $Preferred).Path; Args = @() }
  }
  $python = Resolve-CommandPath "python"
  if ($python) {
    try {
      & $python --version | Out-Null
      if ($LASTEXITCODE -eq 0) { return @{ Exe = $python; Args = @() } }
    } catch {}
  }
  $py = Resolve-CommandPath "py"
  if ($py) {
    try {
      & $py -3 --version | Out-Null
      if ($LASTEXITCODE -eq 0) { return @{ Exe = $py; Args = @("-3") } }
    } catch {}
  }
  throw "Python 3.11+ was not found. Install Python or set LINGJING_PYTHON to a usable python.exe."
}

$node = Resolve-CommandPath "node"
$npm = Resolve-CommandPath "npm"
if (-not $node -or -not $npm) {
  throw "Node.js/npm was not found. Install Node.js 20+ and run this script again."
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
  $pythonCommand = Resolve-Python -Preferred $PythonPath
  Write-Host "Creating Python virtual environment..."
  & $pythonCommand.Exe @($pythonCommand.Args + @("-m", "venv", ".venv"))
}

Write-Host "Checking backend dependencies..."
& $venvPython -c "import fastapi, uvicorn, chromadb, docx, openpyxl, websocket" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing backend dependencies..."
  & $venvPython -m pip install -r backend\requirements.txt
}

if (-not (Test-Path -LiteralPath (Join-Path $Root "node_modules"))) {
  Write-Host "Installing frontend dependencies..."
  npm install
}

Write-Host "Reading scenic package and rebuilding the local knowledge base..."
$env:PYTHONPATH = Join-Path $Root "backend"
& $venvPython -m server.cli rebuild

$backendPort = Resolve-FreePort -Preferred 8000
$frontendPort = Resolve-FreePort -Preferred 3000
$apiBase = "http://127.0.0.1:$backendPort"
$opentalkingSessionEnabled = (Get-DotEnvValue -Name "OPENTALKING_SESSION_ENABLED").ToLowerInvariant()
$opentalkingSessionAutostart = (Get-DotEnvValue -Name "OPENTALKING_SESSION_AUTOSTART").ToLowerInvariant()
$opentalkingSessionBase = Get-DotEnvValue -Name "OPENTALKING_SESSION_BASE_URL"
$opentalkingSessionPython = Get-DotEnvValue -Name "OPENTALKING_SESSION_PYTHON"
$opentalkingSessionAvatarId = Get-DotEnvValue -Name "OPENTALKING_SESSION_AVATAR_ID"
$opentalkingSessionModel = Get-DotEnvValue -Name "OPENTALKING_SESSION_MODEL"
$opentalkingSessionStt = Get-DotEnvValue -Name "OPENTALKING_SESSION_STT_PROVIDER"
$opentalkingSessionTts = Get-DotEnvValue -Name "OPENTALKING_SESSION_TTS_PROVIDER"
if (-not $opentalkingSessionEnabled) { $opentalkingSessionEnabled = "1" }
if (-not $opentalkingSessionAutostart) { $opentalkingSessionAutostart = "1" }
if (-not $opentalkingSessionBase) { $opentalkingSessionBase = "http://127.0.0.1:8210" }
if (-not $opentalkingSessionAvatarId) { $opentalkingSessionAvatarId = "lingjing-guide-quicktalk" }
if (-not $opentalkingSessionModel) { $opentalkingSessionModel = "quicktalk" }
if (-not $opentalkingSessionStt) { $opentalkingSessionStt = "funasr" }
if (-not $opentalkingSessionTts) { $opentalkingSessionTts = "edge" }
if (-not $opentalkingSessionPython) {
  $opentalkingSessionPython = Join-Path $Root "third_party\opentalking\.venv\Scripts\python.exe"
} elseif (-not [System.IO.Path]::IsPathRooted($opentalkingSessionPython)) {
  $opentalkingSessionPython = Join-Path $Root $opentalkingSessionPython
}
if (Test-Path -LiteralPath $opentalkingSessionPython) {
  $opentalkingSessionPython = (Resolve-Path -LiteralPath $opentalkingSessionPython).Path
}
$opentalkingSessionPort = Resolve-PortFromUrl -Url $opentalkingSessionBase -DefaultPort 8210
$opentalkingAutostart = (Get-DotEnvValue -Name "OPENTALKING_AUTOSTART").ToLowerInvariant()
$opentalkingCommand = Get-DotEnvValue -Name "OPENTALKING_INFER_COMMAND"
$opentalkingBase = Get-DotEnvValue -Name "OPENTALKING_BASE_URL"
$opentalkingPython = Get-DotEnvValue -Name "OPENTALKING_PYTHON"
if (-not $opentalkingPython) { $opentalkingPython = $env:OPENTALKING_PYTHON }
if (-not $opentalkingPython) { $opentalkingPython = $venvPython }
if ($opentalkingPython -and (Test-Path -LiteralPath $opentalkingPython)) {
  $opentalkingPython = (Resolve-Path -LiteralPath $opentalkingPython).Path
}
if (-not $opentalkingBase) { $opentalkingBase = "http://127.0.0.1:8011" }
$opentalkingPort = Resolve-PortFromUrl -Url $opentalkingBase -DefaultPort 8011

$runtimeDir = Join-Path $Root "backend\storage"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
@{
  backend_port = $backendPort
  frontend_port = $frontendPort
  opentalking_port = $opentalkingPort
  opentalking_session_port = $opentalkingSessionPort
  api_base = $apiBase
  opentalking_base = $opentalkingBase
  opentalking_session_base = $opentalkingSessionBase
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir "runtime-ports.json") -Encoding UTF8

Write-Host "Building frontend production bundle..."
$env:BACKEND_INTERNAL_URL = $apiBase
$env:NEXT_PUBLIC_API_BASE_URL = ""
Clear-NextBuild
npm run build

$nextCommand = Join-Path $Root "node_modules\.bin\next.cmd"
$backendArgs = @("-m", "uvicorn", "server.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "$backendPort")
$frontendArgs = @("start", "--hostname", "127.0.0.1", "--port", "$frontendPort")
$opentalkingArgs = @("-m", "uvicorn", "server.opentalking_bridge:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "$opentalkingPort")
$opentalkingSessionArgs = @("-m", "apps.unified.main", "--host", "127.0.0.1", "--port", "$opentalkingSessionPort")
$serviceEnv = @{
  PYTHONPATH = (Join-Path $Root "backend")
  BACKEND_INTERNAL_URL = $apiBase
  NEXT_PUBLIC_API_BASE_URL = ""
  OPENTALKING_SESSION_ENABLED = $opentalkingSessionEnabled
  OPENTALKING_SESSION_BASE_URL = $opentalkingSessionBase
}
$opentalkingEnv = @{} + $serviceEnv
$opentalkingSessionEnv = @{
  PYTHONPATH = (Join-Path $Root "third_party\opentalking")
  OPENTALKING_DEFAULT_MODEL = "quicktalk"
  OPENTALKING_QUICKTALK_BACKEND = "local"
  OPENTALKING_TORCH_DEVICE = "cuda:0"
  OPENTALKING_QUICKTALK_DEVICE = "cuda:0"
  OPENTALKING_QUICKTALK_HUBERT_DEVICE = "cuda:0"
  OPENTALKING_DEFAULT_FPS = "25"
  OPENTALKING_QUICKTALK_FPS = "25"
  OPENTALKING_QUICKTALK_SLICE_LEN = "28"
  OPENTALKING_QUICKTALK_RENDER_CHUNK_MS = "500"
  OPENTALKING_QUICKTALK_PREFETCH = "1"
  OPENTALKING_QUICKTALK_WORKER_CACHE = "1"
  OPENTALKING_STT_DEFAULT_PROVIDER = "funasr"
  OPENTALKING_STT_ENABLED_PROVIDERS = "funasr"
  OPENTALKING_STT_PREWARM_ON_STARTUP = "0"
  OPENTALKING_TTS_DEFAULT_PROVIDER = "edge"
  OPENTALKING_TTS_ENABLED_PROVIDERS = "edge"
  OPENTALKING_UNIFIED_UVICORN_WORKERS = "1"
  OPENTALKING_AVATARS_DIR = (Join-Path $Root "backend\storage\opentalking-avatar")
  OPENTALKING_QUICKTALK_ASSET_ROOT = (Join-Path $Root "third_party\opentalking\models\quicktalk")
}

foreach ($name in @(
  "OPENTALKING_SESSION_MODEL",
  "OPENTALKING_SESSION_AVATAR_ID",
  "OPENTALKING_SESSION_STT_PROVIDER",
  "OPENTALKING_SESSION_TTS_PROVIDER",
  "OPENTALKING_QUICKTALK_DEVICE",
  "OPENTALKING_QUICKTALK_HUBERT_DEVICE",
  "OPENTALKING_QUICKTALK_FPS",
  "OPENTALKING_QUICKTALK_SLICE_LEN",
  "OPENTALKING_QUICKTALK_RENDER_CHUNK_MS",
  "OPENTALKING_QUICKTALK_PREFETCH",
  "OPENTALKING_QUICKTALK_WORKER_CACHE"
)) {
  $value = Get-DotEnvValue -Name $name
  if (-not $value) { continue }
  switch ($name) {
    "OPENTALKING_SESSION_MODEL" { $opentalkingSessionEnv["OPENTALKING_DEFAULT_MODEL"] = $value }
    "OPENTALKING_SESSION_STT_PROVIDER" {
      $opentalkingSessionEnv["OPENTALKING_STT_DEFAULT_PROVIDER"] = $value
      $opentalkingSessionEnv["OPENTALKING_STT_ENABLED_PROVIDERS"] = $value
    }
    "OPENTALKING_SESSION_TTS_PROVIDER" {
      $opentalkingSessionEnv["OPENTALKING_TTS_DEFAULT_PROVIDER"] = $value
      $opentalkingSessionEnv["OPENTALKING_TTS_ENABLED_PROVIDERS"] = $value
    }
    "OPENTALKING_SESSION_AVATAR_ID" { }
    default { $opentalkingSessionEnv[$name] = $value }
  }
}

$configuredAvatarsDir = Get-DotEnvValue -Name "OPENTALKING_SESSION_AVATARS_DIR"
if ($configuredAvatarsDir) {
  if (-not [System.IO.Path]::IsPathRooted($configuredAvatarsDir)) {
    $configuredAvatarsDir = Join-Path $Root $configuredAvatarsDir
  }
  $opentalkingSessionEnv["OPENTALKING_AVATARS_DIR"] = $configuredAvatarsDir
}

foreach ($name in @(
  "OPENTALKING_INFER_COMMAND",
  "OPENTALKING_MODEL",
  "OPENTALKING_AVATAR_ID",
  "OPENTALKING_AVATAR_IMAGE",
  "OPENTALKING_AVATAR_DIR",
  "OPENTALKING_OUTPUT_DIR",
  "OPENTALKING_WORKDIR",
  "OPENTALKING_QUICKTALK_ASSET_ROOT",
  "OPENTALKING_QUICKTALK_DEVICE",
  "OPENTALKING_QUICKTALK_HUBERT_DEVICE",
  "OPENTALKING_QUICKTALK_FPS",
  "OPENTALKING_QUICKTALK_MAX_SECONDS",
  "OPENTALKING_QUICKTALK_MAX_TEMPLATE_SECONDS",
  "OPENTALKING_BRIDGE_RENDER_MODE",
  "OPENTALKING_WARMUP",
  "OPENTALKING_WAV2LIP_DEVICE",
  "OPENTALKING_WAV2LIP_FACE_DET_DEVICE",
  "OPENTALKING_WAV2LIP_MODEL_ROOT",
  "OPENTALKING_WAV2LIP_MAX_SECONDS",
  "OPENTALKING_INFER_TIMEOUT"
)) {
  $value = Get-DotEnvValue -Name $name
  if ($value) {
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
    $opentalkingEnv[$name] = $value
  }
}

$opentalkingSessionReady = $false
if (
  $opentalkingSessionEnabled -in @("1", "true", "yes") -and
  $opentalkingSessionAutostart -in @("1", "true", "yes")
) {
  if (-not (Test-Path -LiteralPath $opentalkingSessionPython)) {
    Write-Warning "OpenTalking session runtime was not found at $opentalkingSessionPython. Falling back to standard narration."
  } elseif (-not (Test-PortAvailable -Port $opentalkingSessionPort)) {
    if (Wait-HttpOk -Url "$opentalkingSessionBase/health" -TimeoutSeconds 5) {
      Write-Host "Reusing OpenTalking session service: $opentalkingSessionBase"
      $opentalkingSessionReady = $true
    } else {
      Write-Warning "Port $opentalkingSessionPort is occupied but $opentalkingSessionBase/health is unavailable."
    }
  } else {
    Write-Host "Starting OpenTalking official session + WebRTC service: $opentalkingSessionBase"
    Start-HiddenService -Name "opentalking-session" -FilePath $opentalkingSessionPython -Arguments $opentalkingSessionArgs -Environment $opentalkingSessionEnv
    if (Wait-HttpOk -Url "$opentalkingSessionBase/health" -TimeoutSeconds 60) {
      $opentalkingSessionReady = $true
      Write-Host "OpenTalking session service is ready; QuickTalk avatar prewarm continues in the service."
    } else {
      Write-Warning "OpenTalking session service did not become ready. The application will keep text and Vivo narration available."
    }
  }
}

if ($opentalkingSessionReady) {
  $prewarmScript = Join-Path $Root "scripts\prewarm_opentalking.py"
  if (Test-Path -LiteralPath $prewarmScript) {
    $prewarmArgs = @(
      $prewarmScript,
      "--base-url", $opentalkingSessionBase,
      "--avatar-id", $opentalkingSessionAvatarId,
      "--model", $opentalkingSessionModel,
      "--stt-provider", $opentalkingSessionStt,
      "--tts-provider", $opentalkingSessionTts,
      "--wait-timeout", "180"
    )
    Start-HiddenService -Name "opentalking-prewarm" -FilePath $opentalkingSessionPython -Arguments $prewarmArgs -Environment @{}
    Write-Host "QuickTalk model and avatar prewarm are running in the background; application startup will continue."
  }
}

if (-not $opentalkingSessionReady -and $opentalkingAutostart -in @("1", "true", "yes") -and $opentalkingCommand) {
  if (-not (Test-PortAvailable -Port $opentalkingPort)) {
    if (Wait-HttpOk -Url "$opentalkingBase/api/health" -TimeoutSeconds 5) {
      Write-Host "Reusing running OpenTalking bridge: $opentalkingBase"
    } else {
      throw "OpenTalking bridge port $opentalkingPort is already in use, but $opentalkingBase/api/health is not ready. Stop the old bridge or update OPENTALKING_BASE_URL."
    }
  } else {
    Write-Host "Starting OpenTalking bridge: http://127.0.0.1:$opentalkingPort"
    Start-HiddenService -Name "opentalking" -FilePath $opentalkingPython -Arguments $opentalkingArgs -Environment $opentalkingEnv
    if (-not (Wait-HttpOk -Url "http://127.0.0.1:$opentalkingPort/api/health" -TimeoutSeconds 30)) {
      throw "OpenTalking bridge did not become ready at http://127.0.0.1:$opentalkingPort."
    }
  }
} elseif (-not $opentalkingSessionReady -and $opentalkingAutostart -in @("1", "true", "yes")) {
  Write-Host "OpenTalking autostart is enabled, but OPENTALKING_INFER_COMMAND is empty. The main app will use standard narration."
} elseif ($opentalkingSessionReady) {
  Write-Host "The legacy full-MP4 bridge stays stopped while the WebRTC session path is healthy."
}

Write-Host "Starting backend service: $apiBase"
Start-HiddenService -Name "backend" -FilePath $venvPython -Arguments $backendArgs -Environment $serviceEnv

if (-not (Wait-HttpOk -Url "$apiBase/api/health" -TimeoutSeconds 45)) {
  throw "Backend service did not become ready at $apiBase. Check Python, dependencies, or port permissions."
}

Write-Host "Starting frontend service: http://127.0.0.1:$frontendPort"
Start-HiddenService -Name "frontend" -FilePath $nextCommand -Arguments $frontendArgs -Environment $serviceEnv

if (-not (Wait-HttpOk -Url "http://127.0.0.1:$frontendPort" -TimeoutSeconds 60)) {
  throw "Frontend service did not become ready at http://127.0.0.1:$frontendPort. Check Node.js or port usage."
}

Write-Host ""
Write-Host "Tourist app: http://127.0.0.1:$frontendPort"
Write-Host "Management center: http://127.0.0.1:$frontendPort/admin"
Write-Host "If speech resources are missing, the app uses the scenic knowledge base and local fallback narration."

if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:$frontendPort"
}

if ($KeepAlive) {
  Write-Host ""
  Write-Host "Services are running. Keep this window open; press Ctrl+C to stop."
  while ($true) {
    Start-Sleep -Seconds 3600
  }
}
