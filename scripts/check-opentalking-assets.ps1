param(
  [string]$InstallRoot = "third_party\opentalking"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$target = Join-Path $Root $InstallRoot

$required = @(
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\quicktalk.pth"; MinBytes = 10000000 },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\repair.npy"; MinBytes = 10000 },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\chinese-hubert-large\config.json" },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\chinese-hubert-large\preprocessor_config.json" },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\chinese-hubert-large\pytorch_model.bin"; MinBytes = 10000000 },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\auxiliary\models\det_10g.onnx"; MinBytes = 1000000 },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\auxiliary\models\w600k_r50.onnx"; MinBytes = 1000000 },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\auxiliary\models\buffalo_l\det_10g.onnx"; MinBytes = 1000000 },
  @{ Model = "QuickTalk"; Path = "models\quicktalk\checkpoints\auxiliary\models\buffalo_l\2d106det.onnx"; MinBytes = 1000000 },
  @{ Model = "Wav2Lip"; Path = "models\wav2lip\wav2lip384.pth"; MinBytes = 10000000 },
  @{ Model = "Wav2Lip"; Path = "models\wav2lip\s3fd.pth"; MinBytes = 10000000 }
)

$projectRequired = @(
  @{ Model = "QuickTalk avatar"; Path = "backend\storage\opentalking-avatar\lingjing-guide-quicktalk\manifest.json"; MinBytes = 700 },
  @{ Model = "QuickTalk avatar"; Path = "backend\storage\opentalking-avatar\lingjing-guide-quicktalk\reference.png"; MinBytes = 100000 },
  @{ Model = "QuickTalk avatar"; Path = "backend\storage\opentalking-avatar\lingjing-guide-quicktalk\quicktalk\template_720x720.mp4"; MinBytes = 100000 },
  @{ Model = "Wav2Lip avatar"; Path = "backend\storage\opentalking-avatar\lingjing-guide-wav2lip\manifest.json"; MinBytes = 1000 },
  @{ Model = "Wav2Lip avatar"; Path = "backend\storage\opentalking-avatar\lingjing-guide-wav2lip\reference.png"; MinBytes = 100000 },
  @{ Model = "Wav2Lip avatar"; Path = "backend\storage\opentalking-avatar\lingjing-guide-wav2lip\frames\frame_00000.png"; MinBytes = 100000 }
)

$missing = @()
foreach ($item in $required) {
  $fullPath = Join-Path $target $item.Path
  if (-not (Test-Path -LiteralPath $fullPath)) {
    $missing += [pscustomobject]@{ Model = $item.Model; Path = $item.Path }
    continue
  }
  if ($item.MinBytes) {
    $file = Get-Item -LiteralPath $fullPath
    if ($file.Length -lt [int64]$item.MinBytes) {
      $missing += [pscustomobject]@{ Model = $item.Model; Path = "$($item.Path) (incomplete)" }
    }
  }
}

foreach ($item in $projectRequired) {
  $fullPath = Join-Path $Root $item.Path
  if (-not (Test-Path -LiteralPath $fullPath)) {
    $missing += [pscustomobject]@{ Model = $item.Model; Path = $item.Path }
    continue
  }
  if ($item.MinBytes) {
    $file = Get-Item -LiteralPath $fullPath
    if ($file.Length -lt [int64]$item.MinBytes) {
      $missing += [pscustomobject]@{ Model = $item.Model; Path = "$($item.Path) (incomplete)" }
    }
  }
}

if ($missing.Count -gt 0) {
  Write-Host "OpenTalking model assets are incomplete:"
  $missing | Format-Table -AutoSize | Out-String | Write-Host
  exit 1
}

Write-Host "OpenTalking QuickTalk, Wav2Lip weights, and Lingjing QuickTalk/Wav2Lip avatar assets are present."
