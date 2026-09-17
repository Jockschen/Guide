# OpenTalking 数字人配置与验收

项目实时主链路是 **Edge 中文语音 → OpenTalking session → QuickTalk → WebRTC**。系统不再等待整段 MP4 生成后播放；浏览器先建立持续流，回答音频生成后直接上传同一个 session 驱动口型。

## 运行链路

```text
游客文本 / 语音 / 图片
  → 本地景区资料检索
  → Qwen 或本地资料回答
  → Edge 中文语音（语速、音量真实生效）
  → OpenTalking session 音频入队
  → QuickTalk 常驻 worker
  → WebRTC 持续音视频
```

降级顺序是 `session → remote → legacy_mp4 → audio_only`：

- `session` 是当前演示主链路。
- `remote` 是以后连接 FlashTalk / FlashHead 等高质量远程服务的扩展位，当前不宣称已部署。
- `legacy_mp4` 仅用于兼容或录屏。
- `audio_only` 在数字人不可用时保留语音和字幕，不把静态动画冒充真实口型。

## RTX 4060 8GB 配置

- 模型：QuickTalk
- 设备：`cuda:0`
- 形象尺寸：720 × 720
- 目标帧率：25fps
- 模板：60 帧、约 2.4 秒，可循环待机
- 切片长度：28
- 渲染分块：500ms
- worker cache、模型预热、形象预热：开启

这是本项目演示机配置，不是对所有 4060、所有素材和所有并发负载的通用性能承诺。MuseTalk 或其他高显存方案不在本机 8GB 显存的承诺范围内；需要更高质量时应通过远程 Provider 扩展。

## 管理员只需上传一张图

后台“数字人形象”只维护一个当前数字人，不再让管理员理解版本、模型 ID、服务地址或预热状态。

1. 上传一张有授权的正面半身形象图。
2. 填写显示名称和人设。
3. 选择中文声音并点击“试听声音”。
4. 点击“保存并应用”。

系统在后台自动完成图片缩放、QuickTalk 形象准备、预热和游客端配置切换。建议图片满足：正面或轻微侧面、嘴唇自然闭合、无遮挡、光线均匀、背景简洁。单图生成的循环素材降低了维护门槛；最终自然度仍以专家观看演示视频的评价为准。

当前默认形象：

- 源图：`public/assets/generated/avatar-guide-v2.png`
- QuickTalk 目录：`backend/storage/opentalking-avatar/lingjing-guide-quicktalk`
- 画面：720 × 720、25fps、60 帧

## 推荐环境变量

```env
# 中文语音主线
TTS_PROVIDER=edge

# OpenTalking session + WebRTC
OPENTALKING_SESSION_ENABLED=1
OPENTALKING_SESSION_AUTOSTART=1
OPENTALKING_SESSION_BASE_URL=http://127.0.0.1:8210
OPENTALKING_SESSION_MODEL=quicktalk
OPENTALKING_SESSION_AVATAR_ID=lingjing-guide-quicktalk
OPENTALKING_SESSION_PYTHON=third_party/opentalking/.venv/Scripts/python.exe
OPENTALKING_SESSION_TIMEOUT_SECONDS=45
OPENTALKING_SESSION_AVATARS_DIR=backend/storage/opentalking-avatar

# RTX 4060 8GB 演示档
OPENTALKING_QUICKTALK_DEVICE=cuda:0
OPENTALKING_QUICKTALK_HUBERT_DEVICE=cuda:0
OPENTALKING_QUICKTALK_FPS=25
OPENTALKING_QUICKTALK_SLICE_LEN=28
OPENTALKING_QUICKTALK_RENDER_CHUNK_MS=500
OPENTALKING_QUICKTALK_PREFETCH=1
OPENTALKING_QUICKTALK_WORKER_CACHE=1

# 可选远程高质量扩展
OPENTALKING_REMOTE_PROVIDER_BASE_URL=
OPENTALKING_REMOTE_PROVIDER_MODEL=flashtalk

# 旧 MP4 桥接关闭
OPENTALKING_AUTOSTART=0
OPENTALKING_BASE_URL=
```

Edge 中文语音不要求 API Key。当前预设把温和讲解、沉稳讲解等游客语言映射为合适的中文神经网络声音；前端语速和音量会同时传给语音生成，并在当前播放器中即时生效。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -NoBrowser
```

看到下面两行不是“卡住”，表示 session 服务已就绪，预热在后台继续：

```text
OpenTalking session service is ready; QuickTalk avatar prewarm continues in the service.
QuickTalk model and avatar prewarm are running in the background; application startup will continue.
```

游客页会先显示准备状态，形象进入 `worker_ready` 后建立 WebRTC。停止服务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

## 四层验收

### 1. 服务存活

```powershell
Invoke-RestMethod http://127.0.0.1:8210/health
Invoke-RestMethod http://127.0.0.1:8000/api/avatar/session-capability
```

能力接口应返回 session、WebRTC、QuickTalk 和当前形象可用。页面上只显示“数字人已就绪”等中文状态，不显示这些技术字段。

### 2. 形象与模型就绪

查看 `backend/storage/logs/opentalking-prewarm.latest.log` 及其指向的日志。成功口径是 `ready` 或 `worker_ready`，并以退出码 0 结束；只看 `/health=ok` 不足以证明形象已加载。

### 3. WebRTC 真实视频帧

必须实际创建 session、等到 worker ready、发送 WebRTC offer，并从 track 收到首个可播放视频帧。静态海报、字幕或 CSS 动画不算通过。

### 4. 音频驱动的可见口型

向同一个 session 上传有效 PCM WAV，确认进入 speaking、连续帧不是冻结画面、嘴部区域变化明显，播完后可回到待机并继续下一次讲解。

## 当前真实联调结果

报告：`reports/quality/opentalking-webrtc-latest.json`

| 检查项 | 当前结果 |
| --- | ---: |
| 创建 session 到首个视频帧 | 741.9 ms |
| 音频上传接口耗时 | 85.4 ms |
| 音频上传到 speaking | 180.0 ms |
| 音频上传到可见嘴部运动 | 2364.5 ms |
| speaking 采样帧 | 128 帧 |
| speaking 唯一帧 | 128 帧 |
| 嘴部帧差平均 / P95 / 峰值 | 0.9336 / 3.4602 / 7.5074 |

报告的六项检查——视频轨、连接、speaking、足够连续帧、画面非冻结、可见嘴部运动——全部通过。对比图片在：

- `reports/quality/opentalking-webrtc-evidence/mouth-before.png`
- `reports/quality/opentalking-webrtc-evidence/mouth-motion-peak.png`

这证明当前样本的数字人确实会动且嘴部会随音频出现明显变化；它不是专家自然度评分，也不能单独证明完整问答都低于 5 秒。

### 严格端到端验收

旧 `reports/quality/e2e-latency-latest.json` 的阶段合计为 `17738.99 ms`，并缺少 ASR 和浏览器 `first_visible_mouth_ms`，所以 `measurement_complete=false`。它不能证明端到端低于 5 秒。

赛前打开游客页 `/?benchmark=1`，等待 session 预热后由真人完成 30 次语音提问。控制台先执行 `window.__LINGJING_E2E_BENCHMARK__.clear()`，完成后用 `.getSamples()` 检查数量并用 `.download()` 导出 JSON，再运行默认 strict live 验收：

```powershell
$env:COMPETITION_E2E_SAMPLE_FILE="reports/quality/browser-e2e-samples.json"
npm run competition-check

# 只做离线静态回归，不构成赛事证据
npm run competition-check:static
```

采集器用 `requestVideoFrameCallback + canvas` 检测 WebRTC 嘴部 ROI，音频侧要求真实 `HTMLAudioElement playing`，PCM WAV 还会估算首个非静音样本偏移。权威总时延是 `max(首个有效音频, 首个可见口型)-录音停止`；阶段值只做诊断，不能相加。只有 30 次样本全部完整、真实 provider、`session_stream`、成功率 100% 且 P95 <5 秒才可表述为本地端到端目标达标。当前这组现场报告尚未生成。

时延证据与问答准确率证据必须分开：固定 17 题当前为 `17/17 = 100%`；30 题独立隐藏本地题集完整自测为 `28/30 = 93.33%`、请求成功率 `100%`。两者都保持 `official_evaluation=false`，不能表述为比赛官方准确率；最后两题定向复测通过也不能代替完整 30 题重跑。

## 常见故障

### 页面看到两个人像

- WebRTC 视频出现后，静态海报必须隐藏，不能与视频层叠显示。
- 背景图不应再放第二个近景人物；远景景区雕塑属于场景元素，但也应避免抢占数字人视觉焦点。
- 浏览器仍显示旧样式时，先关闭旧端口进程并强制刷新当前构建。

### 页面能看到形象但不动

1. 检查能力接口是否可用。
2. 确认 session 已到 `worker_ready`，不要把 `created` 当成就绪。
3. 检查当前形象 ID 与目录 manifest 一致。
4. 确认模板不是 1 帧文件；默认模板应有 60 帧。
5. 确认浏览器已建立 RTCPeerConnection，而不是停留在海报层。
6. 使用有效 PCM WAV 单独验证音频上传，避免把语音和数字人两个故障混在一起。

### 中文语音没有声音

- 当前默认是 Edge 中文语音，不依赖 Vivo 凭据。
- 检查 `/api/tts/synthesize` 是否返回真实 `audio_url`，以及生成文件是否是 PCM WAV。
- 语速和音量既影响生成参数，也会即时更新当前播放器；测试时使用明显差异（如 0.8× / 1.2×、30% / 100%）。
- Edge 暂时不可用时可以切到本地语音适配器，但不能把 mock 或空音频用于口型验收。

### 显存不足或速度不稳

- 保持 QuickTalk、720 × 720、25fps，不在同一张 8GB 显卡并行加载未验证的高显存模型。
- 保持 worker cache 和预热，避免每轮问答重新加载模型。
- 重新启动后检查最新预热日志和真实 WebRTC 报告，不只看启动窗口文字。

## 参赛材料的准确表述

- 可以说“已接入 OpenTalking 官方 session + WebRTC，并用 Edge 中文语音完成真实音频驱动；联调报告证明 128 个说话帧全部唯一且嘴部有可见运动”。
- 可以说“当前样本创建 session 到首帧 741.9 ms，音频上传到可见嘴部运动 2364.5 ms”。
- 不应说“所有问题完整响应都低于 5 秒”；旧报告为 17.74 秒且不完整，新的 30 次 P95 <5 秒仍待现场实测。
- 不应把像素帧差当作专家自然度评分；最终自然度由比赛专家看演示视频评定。
