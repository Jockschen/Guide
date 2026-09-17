param(
  [int]$Port = 8011,
  [string]$PythonPath = $env:LINGJING_PYTHON
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

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

$opentalkingEnvNames = @(
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
)

foreach ($name in $opentalkingEnvNames) {
  $value = Get-DotEnvValue -Name $name
  if ($value) {
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not $PythonPath) {
  $PythonPath = Get-DotEnvValue -Name "OPENTALKING_PYTHON"
}
if ($PythonPath -and (Test-Path -LiteralPath $PythonPath)) {
  $venvPython = $PythonPath
} elseif (-not (Test-Path -LiteralPath $venvPython)) {
  throw "Python environment was not found. Run start.bat first to install the base dependencies, or set OPENTALKING_PYTHON."
}

if (-not $env:OPENTALKING_INFER_COMMAND) {
  Write-Host "OPENTALKING_INFER_COMMAND is not configured."
  Write-Host "Set a QuickTalk/Wav2Lip/FlashTalk inference command in PowerShell or .env first."
  Write-Host "Supported placeholders: {audio} {image} {avatar} {text} {output} {model}"
  Write-Host ""
  Write-Host "Example:"
  Write-Host '$env:OPENTALKING_INFER_COMMAND="python your_infer.py --audio ""{audio}"" --image ""{image}"" --outfile ""{output}"""'
  Write-Host ""
}

$env:PYTHONPATH = Join-Path $Root "backend"
$env:OPENTALKING_OUTPUT_DIR = if ($env:OPENTALKING_OUTPUT_DIR) { $env:OPENTALKING_OUTPUT_DIR } else { Join-Path $Root "backend\storage\opentalking-output" }
Write-Host "OpenTalking bridge: http://127.0.0.1:$Port"
Write-Host "Set OPENTALKING_BASE_URL=http://127.0.0.1:$Port in .env for the main app."
& $venvPython -m uvicorn server.opentalking_bridge:app --app-dir backend --host 127.0.0.1 --port $Port
