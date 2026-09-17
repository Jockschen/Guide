param(
  [string]$InstallRoot = "third_party\opentalking",
  [string]$PythonPath = $env:OPENTALKING_PYTHON,
  [ValidateSet("cpu", "cuda")]
  [string]$Device = "cpu",
  [string]$TorchCudaIndex = "https://download.pytorch.org/whl/cu128"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$target = Join-Path $Root $InstallRoot
if (-not (Test-Path -LiteralPath (Join-Path $target "pyproject.toml"))) {
  throw "OpenTalking repository was not found under $target. Run npm run opentalking:setup first."
}

function Resolve-Python {
  param([string]$Preferred)
  if ($Preferred -and (Test-Path -LiteralPath $Preferred)) {
    return @{ File = (Resolve-Path -LiteralPath $Preferred).Path; Args = @() }
  }
  $py = Get-Command "py" -ErrorAction SilentlyContinue
  if ($py) {
    foreach ($version in @("-3.11", "-3.12", "-3.10", "-3")) {
      try {
        & $py.Source $version --version *> $null
        if ($LASTEXITCODE -eq 0) { return @{ File = $py.Source; Args = @($version) } }
      } catch {
        continue
      }
    }
  }
  $python = Get-Command "python" -ErrorAction SilentlyContinue
  if ($python) { return @{ File = $python.Source; Args = @() } }
  throw "Python 3.10+ was not found. Install Python first or set OPENTALKING_PYTHON."
}

function Invoke-Python {
  param($PythonCommand, [string[]]$Arguments)
  & $PythonCommand.File @($PythonCommand.Args + $Arguments)
}

$venv = Join-Path $target ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
  $pythonCommand = Resolve-Python -Preferred $PythonPath
  Write-Host "Creating OpenTalking Python environment..."
  Invoke-Python -PythonCommand $pythonCommand -Arguments @("-m", "venv", $venv)
}

Write-Host "Installing OpenTalking runtime dependencies..."
& $venvPython -m pip install -U pip setuptools wheel
$extras = if ($Device -eq "cuda") { "models,quicktalk-cuda" } else { "models,quicktalk-cpu" }
Push-Location $target
try {
  & $venvPython -m pip install -e ".[$extras]"
} finally {
  Pop-Location
}

if ($Device -eq "cuda") {
  Write-Host "Installing CUDA PyTorch wheels..."
  & $venvPython -m pip install --force-reinstall --no-deps --index-url $TorchCudaIndex torch torchvision torchaudio

  Write-Host "Installing CUDA ONNX Runtime..."
  & $venvPython -m pip install "onnxruntime==1.26.0" "onnxruntime-gpu==1.26.0" "setuptools<82"
  & $venvPython -m pip install --force-reinstall --no-deps "onnxruntime-gpu==1.26.0"
}

Write-Host "Checking OpenTalking runtime..."
& $venvPython -c "import cv2, torch, opentalking; print('cv2 ok'); print('torch', torch.__version__)"

Write-Host ""
Write-Host "Runtime is ready. Add this to .env:"
Write-Host "OPENTALKING_PYTHON=$venvPython"
if ($Device -eq "cuda") {
  Write-Host "OPENTALKING_MODEL=quicktalk"
  Write-Host "OPENTALKING_AVATAR_DIR=backend/storage/opentalking-avatar/lingjing-guide-quicktalk"
  Write-Host "OPENTALKING_QUICKTALK_ASSET_ROOT=models/quicktalk"
  Write-Host "OPENTALKING_QUICKTALK_DEVICE=cuda:0"
  Write-Host "OPENTALKING_QUICKTALK_HUBERT_DEVICE=cuda:0"
  Write-Host "OPENTALKING_QUICKTALK_FPS=25"
  Write-Host "OPENTALKING_QUICKTALK_MAX_SECONDS=0"
  Write-Host "OPENTALKING_QUICKTALK_MAX_TEMPLATE_SECONDS=2.4"
  Write-Host "OPENTALKING_WAV2LIP_DEVICE=cuda"
  Write-Host "OPENTALKING_WAV2LIP_FACE_DET_DEVICE=cuda"
  Write-Host "OPENTALKING_WAV2LIP_MODEL_ROOT=models/wav2lip"
  Write-Host "OPENTALKING_WAV2LIP_MAX_SECONDS=0"
  Write-Host "OPENTALKING_INFER_COMMAND={pythonq} ..\..\scripts\opentalking_quicktalk_gpu_render.py --avatar-dir `"{avatar}`" --audio `"{audio}`" --output `"{output}`" --device cuda:0"
} else {
  Write-Host "OPENTALKING_MODEL=quicktalk"
  Write-Host "OPENTALKING_AVATAR_DIR=backend/storage/opentalking-avatar/lingjing-guide-quicktalk"
  Write-Host "OPENTALKING_QUICKTALK_ASSET_ROOT=models/quicktalk"
  Write-Host "OPENTALKING_QUICKTALK_DEVICE=cpu"
  Write-Host "OPENTALKING_QUICKTALK_HUBERT_DEVICE=cpu"
  Write-Host "OPENTALKING_QUICKTALK_FPS=25"
  Write-Host "OPENTALKING_QUICKTALK_MAX_SECONDS=0"
  Write-Host "OPENTALKING_QUICKTALK_MAX_TEMPLATE_SECONDS=2.4"
  Write-Host "OPENTALKING_WAV2LIP_DEVICE=cpu"
  Write-Host "OPENTALKING_WAV2LIP_FACE_DET_DEVICE=cpu"
  Write-Host "OPENTALKING_WAV2LIP_MODEL_ROOT=models/wav2lip"
  Write-Host "OPENTALKING_WAV2LIP_MAX_SECONDS=0"
  Write-Host "OPENTALKING_INFER_COMMAND={pythonq} ..\..\scripts\opentalking_quicktalk_gpu_render.py --avatar-dir `"{avatar}`" --audio `"{audio}`" --output `"{output}`" --device cpu"
}
