param(
  [int]$BackendPort = 8031,
  [int]$FrontendPort = 3031
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) {
    throw $Message
  }
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

function Invoke-JsonPost {
  param([string]$Url, [string]$Body)
  return Invoke-WebRequest -Uri $Url -Method Post -Body $Body -ContentType "application/json; charset=utf-8" -UseBasicParsing -TimeoutSec 25
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
Assert-True (Test-Path -LiteralPath $venvPython) "未找到 .venv\Scripts\python.exe，请先运行 start.bat 完成依赖安装。"

Write-Host "1/6 类型检查"
npm run typecheck

Write-Host "2/6 后端测试"
& $venvPython -m unittest discover -s backend\tests -p "test_*.py"

Write-Host "3/6 生产构建"
npm run build

$backendJob = $null
$frontendJob = $null
try {
  Write-Host "4/6 启动后端并检查核心接口"
  $backendJob = Start-Job -ScriptBlock {
    param($RootPath, $Port)
    Set-Location -LiteralPath $RootPath
    $env:PYTHONPATH = Join-Path $RootPath "backend"
    $pythonExe = Join-Path $RootPath ".venv\Scripts\python.exe"
    & $pythonExe -m uvicorn server.main:app --app-dir backend --host 127.0.0.1 --port $Port
  } -ArgumentList $Root,$BackendPort

  $backendBase = "http://127.0.0.1:" + [string]$BackendPort
  $backendHealthUrl = $backendBase + "/api/health"
  $pipelineUrl = $backendBase + "/api/admin/pipeline-check"
  $ttsUrl = $backendBase + "/api/tts/synthesize"
  $asrUrl = $backendBase + "/api/asr/transcribe"
  Assert-True (Wait-HttpOk -Url $backendHealthUrl -TimeoutSeconds 45) "后端健康接口未就绪。"

  $health = (Invoke-WebRequest -Uri $backendHealthUrl -UseBasicParsing -TimeoutSec 10).Content | ConvertFrom-Json
  Assert-True ($health.ok -eq $true) "后端健康接口返回异常。"
  Assert-True ([string]::IsNullOrWhiteSpace($health.asr_effective_provider) -eq $false) "语音输入运行模式为空。"
  Assert-True ([string]::IsNullOrWhiteSpace($health.tts_effective_provider) -eq $false) "语音合成运行模式为空。"

  $pipeline = (Invoke-WebRequest -Uri $pipelineUrl -UseBasicParsing -TimeoutSec 25).Content | ConvertFrom-Json
  Assert-True ($pipeline.ok -eq $true) "链路自检接口返回异常。"
  Assert-True ($pipeline.data.knowledge_ready -eq $true) "链路自检未检索到知识库内容。"
  Assert-True ([int]$pipeline.data.visemes_count -gt 0) "链路自检未生成口型帧。"

  $tts = (Invoke-JsonPost -Url $ttsUrl -Body '{"text":"欢迎来到灵山胜境","voice":"gentle","style":"自然讲解","speed":1,"volume":0.8}').Content | ConvertFrom-Json
  Assert-True ($tts.ok -eq $true) "TTS 适配层接口返回异常。"
  Assert-True ([string]::IsNullOrWhiteSpace($tts.data.provider) -eq $false) "TTS 适配层未返回运行模式。"

  $boundary = "----LingjingSelfCheckBoundary"
  $asrBody = "--$boundary`r`nContent-Disposition: form-data; name=`"file`"; filename=`"question.webm`"`r`nContent-Type: audio/webm`r`n`r`nabc`r`n--$boundary--`r`n"
  $asr = (Invoke-WebRequest -Uri $asrUrl -Method Post -Body $asrBody -ContentType "multipart/form-data; boundary=$boundary" -UseBasicParsing -TimeoutSec 25).Content | ConvertFrom-Json
  Assert-True ($asr.ok -eq $true) "ASR 适配层接口返回异常。"
  Assert-True ([string]::IsNullOrWhiteSpace($asr.data.text) -eq $false) "ASR 保底文本为空，无法完成语音演示闭环。"

  Write-Host "5/6 启动前端并检查页面与代理"
  $frontendJob = Start-Job -ScriptBlock {
    param($RootPath, $ApiBase, $Port)
    Set-Location -LiteralPath $RootPath
    $env:BACKEND_INTERNAL_URL = $ApiBase
    $env:NEXT_PUBLIC_API_BASE_URL = ""
    $nextCommand = Join-Path $RootPath "node_modules\.bin\next.cmd"
    & $nextCommand start --hostname 127.0.0.1 --port $Port
  } -ArgumentList $Root,$backendBase,$FrontendPort

  $frontendBase = "http://127.0.0.1:" + [string]$FrontendPort
  $adminUrl = $frontendBase + "/admin"
  $proxyPipelineUrl = $frontendBase + "/api/admin/pipeline-check"
  Assert-True (Wait-HttpOk -Url $frontendBase -TimeoutSeconds 60) "前端首页未就绪。"
  $tourist = Invoke-WebRequest -Uri $frontendBase -UseBasicParsing -TimeoutSec 10
  Assert-True ($tourist.StatusCode -eq 200) "游客端访问失败。"
  $admin = Invoke-WebRequest -Uri $adminUrl -UseBasicParsing -TimeoutSec 10
  Assert-True ($admin.StatusCode -eq 200) "管理中心访问失败。"
  $proxy = (Invoke-WebRequest -Uri $proxyPipelineUrl -UseBasicParsing -TimeoutSec 25).Content | ConvertFrom-Json
  Assert-True ($proxy.ok -eq $true) "前端 API 代理链路自检失败。"

  Write-Host "6/6 自检完成"
  [pscustomobject]@{
    backend = $backendBase
    frontend = $frontendBase
    asr = $health.asr_effective_provider
    tts = $health.tts_effective_provider
    knowledge_chunks = $pipeline.data.retrieved_chunks
    visemes = $pipeline.data.visemes_count
  } | ConvertTo-Json -Compress
} finally {
  if ($frontendJob) {
    Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
    Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue | Select-Object -Last 10
    Remove-Job -Job $frontendJob -Force -ErrorAction SilentlyContinue
  }
  if ($backendJob) {
    Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
    Receive-Job -Job $backendJob -ErrorAction SilentlyContinue | Select-Object -Last 10
    Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue
  }
}
