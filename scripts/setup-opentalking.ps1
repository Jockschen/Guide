param(
  [ValidateSet("quicktalk", "wav2lip", "all")]
  [string]$Model = "all",
  [string]$InstallRoot = "third_party\opentalking",
  [switch]$SkipRepo,
  [switch]$SkipWeights
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Ensure-Directory([string]$Path) {
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Download-File([string]$Url, [string]$Output) {
  if (Test-Path -LiteralPath $Output) {
    $existing = Get-Item -LiteralPath $Output
    if ($existing.Length -gt 4096) {
      Write-Host "Already exists: $Output"
      return
    }
    Write-Host "Removing incomplete download: $Output"
    Remove-Item -LiteralPath $Output -Force
  }
  Ensure-Directory (Split-Path -Parent $Output)
  Write-Host "Downloading: $Url"
  $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
  if ($curl) {
    & $curl.Source -L --fail --retry 3 --retry-delay 2 -o $Output $Url
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $Output)) { return }
    Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
  }
  Invoke-WebRequest -Uri $Url -OutFile $Output -UseBasicParsing -MaximumRedirection 10 -Headers @{ "User-Agent" = "Mozilla/5.0" }
}

function Resolve-HfCommand {
  $hf = Get-Command "hf" -ErrorAction SilentlyContinue
  if ($hf) { return $hf.Source }
  $legacy = Get-Command "huggingface-cli" -ErrorAction SilentlyContinue
  if ($legacy) { return $legacy.Source }
  return $null
}

function Download-HfFile([string]$Repo, [string]$File, [string]$OutputRoot) {
  $output = Join-Path $OutputRoot $File
  if (Test-Path -LiteralPath $output) {
    $existing = Get-Item -LiteralPath $output
    $minBytes = if ([System.IO.Path]::GetExtension($File).ToLowerInvariant() -eq ".json") { 32 } else { 4096 }
    if ($existing.Length -gt $minBytes) {
      Write-Host "Already exists: $output"
      return
    }
    Write-Host "Removing incomplete download: $output"
    Remove-Item -LiteralPath $output -Force
  }
  Ensure-Directory (Split-Path -Parent $output)
  $hf = Resolve-HfCommand
  if ($hf) {
    Write-Host "Downloading from Hugging Face: $Repo/$File"
    & $hf download $Repo $File --local-dir $OutputRoot
    return
  }
  $hfEndpoint = $env:HF_ENDPOINT
  if (-not $hfEndpoint) { $hfEndpoint = "https://huggingface.co" }
  $url = "$($hfEndpoint.TrimEnd('/'))/$Repo/resolve/main/$File"
  Download-File $url $output
}

$target = Join-Path $Root $InstallRoot
Ensure-Directory (Split-Path -Parent $target)

if (-not $SkipRepo) {
  if (-not (Test-Path -LiteralPath (Join-Path $target ".git"))) {
    git clone --depth 1 https://github.com/datascale-ai/opentalking.git $target
  } else {
    Write-Host "OpenTalking repo already exists: $target"
  }
}

if ($SkipWeights) {
  Write-Host "Skipped model weights."
  exit 0
}

if ($Model -in @("quicktalk", "all")) {
  $quicktalkRoot = Join-Path $target "models\quicktalk\checkpoints"
  Download-HfFile "datascale-ai/quicktalk" "quicktalk.pth" $quicktalkRoot
  Download-HfFile "datascale-ai/quicktalk" "repair.npy" $quicktalkRoot
  Download-HfFile "datascale-ai/quicktalk" "chinese-hubert-large/config.json" $quicktalkRoot
  Download-HfFile "datascale-ai/quicktalk" "chinese-hubert-large/preprocessor_config.json" $quicktalkRoot
  Download-HfFile "datascale-ai/quicktalk" "chinese-hubert-large/pytorch_model.bin" $quicktalkRoot
  $buffaloZip = Join-Path $quicktalkRoot "buffalo_l.zip"
  Download-File "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip" $buffaloZip
  $buffaloTarget = Join-Path $quicktalkRoot "auxiliary\models"
  Ensure-Directory $buffaloTarget
  if (-not (Test-Path -LiteralPath (Join-Path $buffaloTarget "buffalo_l"))) {
    Expand-Archive -LiteralPath $buffaloZip -DestinationPath $buffaloTarget -Force
  }
}

if ($Model -in @("wav2lip", "all")) {
  $wav2lipRoot = Join-Path $target "models\wav2lip"
  Download-HfFile "Pypa/wav2lip384" "wav2lip384.pth" $wav2lipRoot
  Download-HfFile "rippertnt/wav2lip" "s3fd.pth" $wav2lipRoot
}

Write-Host ""
Write-Host "OpenTalking assets are ready under: $target"
Write-Host "Set OPENTALKING_BASE_URL in .env after starting the OpenTalking service."
