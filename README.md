# 灵境导游：面向智慧景区的多模态 AI 数字人导览系统

项目面向文旅景区的游客导览和运营管理：游客可以通过文本、语音和图片与数字人交互，获取基于景区资料的讲解和个性化推荐游线；管理方可以维护知识、上传一张数字人形象图、试听声音、处理游客反馈并查看质量报告。

## 当前版本的主线

- 问答：本地灵山胜境知识检索 + Qwen OpenAI 兼容接口；无 Key 时保留资料增强的本地回答。
- 语音：默认使用 Edge 中文神经网络语音，提供自然女声/男声并真实响应语速和音量；ASR/TTS 适配层仍保留 Vivo、FunASR、CosyVoice、sherpa-onnx 和 Piper 扩展。
- 数字人：首选 OpenTalking 官方 session + WebRTC，主应用把 Qwen + 知识库回答生成的 TTS 音频上传 session 驱动 QuickTalk。
- 显卡档：针对 RTX 4060 8GB 配置 QuickTalk、720p 级别画布、25fps、worker cache 和形象/模型预热。这是本项目的目标配置，不是对任意 4060 环境的帧率保证。
- 兼容降级：`session → remote → legacy_mp4 → audio_only`；旧整段 MP4 桥接不再是实时主方案。
- 游线：保留规划能力并改名为“个性化推荐游线”，回答内显示摘要，右侧以“对话 / 当前游线”切换完整地图，手机端使用全宽视图。

详细链路、形象素材要求和故障排查见 [OpenTalking 数字人配置与验收](docs/digital-human-setup.md)。比赛要求的真实完成度见 [赛题要求验收矩阵](docs/competition-requirements-audit.md)。

## 技术栈

- 前端：Next.js 15、React 19、TypeScript、Lucide Icons
- 后端：FastAPI、SQLite
- 知识库：Chroma 优先，SQLite FTS/检索兜底，保留 FAISS 可选入口
- 大模型：Qwen OpenAI 兼容接口
- 语音：Edge 中文神经网络语音为当前 TTS 主线；Vivo ASR 和本地语音方案作为可选适配器
- 数字人：OpenTalking QuickTalk 官方 session + WebRTC；旧 MP4 桥接仅兼容兜底

## 赛题对齐

项目对应赛题中的主要业务问题：

- 用 7×24 数字人缓解旺季导游人力紧张。
- 用本地景区知识库和互动问答替代单向录音导览。
- 用语音、表情和实时口型增强情感连接。
- 用反馈、情感趋势、热门问答和质量报告补足景区运营盲区。

当前不把研发自测包装成官方评测结论：最新固定 17 题自测为 `17/17 = 100%`，独立隐藏 30 题完整自测为 `28/30 = 93.33%`、请求成功率 `100%`；两者都只是本地结果，不是比赛官方测试集成绩。最新 OpenTalking WebRTC 联调记录首个视频帧 `741.9 ms`、音频上传到 speaking `180.0 ms`、音频上传到可见口型变化 `2364.5 ms`。旧端到端报告的阶段合计为 `17.74 s`，且缺少 ASR 与浏览器首个可见口型，`measurement_complete=false`；新的 30 次真实样本 `P95 < 5 s` 仍待比赛机器现场实测。

## 一键启动

### 环境

- Node.js 20+
- Python 3.11+
- 如启用 QuickTalk GPU：安装可匹配的 NVIDIA 驱动、CUDA/PyTorch 运行时

### 首次准备

1. 复制 `.env.example` 为 `.env`，填入需要的 API 凭据。
2. 准备 OpenTalking 权重和独立运行时：

```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
npm run opentalking:setup
npm run opentalking:runtime
npm run opentalking:check
```

### 启动与停止

双击 `start.bat`，或运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -NoBrowser
```

默认地址：

- 游客端：`http://127.0.0.1:3000`
- 管理中心：`http://127.0.0.1:3000/admin`
- FastAPI 文档：`http://127.0.0.1:8000/docs`
- OpenTalking session：`http://127.0.0.1:8210`

如 3000 或 8000 被占用，脚本会选择邻近空闲端口，并写入 `backend/storage/runtime-ports.json`。前端通过同源 `/api/*` 代理访问 FastAPI。

启动时 OpenTalking 预热会在后台继续，不再阻塞主应用。看到下列文字后，FastAPI 和 Next.js 应继续启动：

```text
OpenTalking session service is ready; QuickTalk avatar prewarm continues in the service.
QuickTalk model and avatar prewarm are running in the background; application startup will continue.
```

停止：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

重新打开页面无需重启服务，可双击 `open.bat`。

## `.env` 核心项

```env
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.5-omni-plus-2026-03-15

ASR_PROVIDER=vivo
TTS_PROVIDER=edge
VIVO_APP_ID=
VIVO_APP_KEY=

# OpenTalking session + WebRTC 主链路
OPENTALKING_SESSION_ENABLED=1
OPENTALKING_SESSION_AUTOSTART=1
OPENTALKING_SESSION_BASE_URL=http://127.0.0.1:8210
OPENTALKING_SESSION_MODEL=quicktalk
OPENTALKING_SESSION_AVATAR_ID=lingjing-guide-quicktalk
OPENTALKING_SESSION_PYTHON=third_party/opentalking/.venv/Scripts/python.exe
OPENTALKING_SESSION_AVATARS_DIR=backend/storage/opentalking-avatar

OPENTALKING_QUICKTALK_DEVICE=cuda:0
OPENTALKING_QUICKTALK_HUBERT_DEVICE=cuda:0
OPENTALKING_QUICKTALK_FPS=25
OPENTALKING_QUICKTALK_SLICE_LEN=28
OPENTALKING_QUICKTALK_RENDER_CHUNK_MS=500
OPENTALKING_QUICKTALK_PREFETCH=1
OPENTALKING_QUICKTALK_WORKER_CACHE=1

# 远程高质量扩展；未部署时保持为空
OPENTALKING_REMOTE_PROVIDER_BASE_URL=
OPENTALKING_REMOTE_PROVIDER_MODEL=flashtalk

# 旧整段 MP4 桥接只作兼容兜底
OPENTALKING_AUTOSTART=0
OPENTALKING_BASE_URL=
```

`.env.example` 保留了完整 Provider 配置。凭据不应出现在截图、文档、日志或提交包中。

## 语音与数字人链路

```text
游客输入
→ ASR（语音场景）
→ 本地景区资料检索
→ Qwen 或本地检索回答
→ 主应用 TTS
→ 上传音频到 OpenTalking session
→ QuickTalk 常驻 worker
→ WebRTC 持续视频
```

游客端只展示音色、讲解风格、语速、音量、字幕和播报控制，不把 Provider 名称和服务地址暴露给游客。

当 session 不可用时，前端保留语音、字幕和干净待机舞台。只有真实 WebRTC 或真实视频结果可以标记为真实口型，CSS 波形和待机表情不代替口型同步证据。

## 个性化推荐游线

规划功能作为景区导览的核心能力保留，但不再作为第三个网格子项追加到长页底部。

- 问答回答内显示紧凑游线摘要。
- 右侧对话区使用“对话 / 当前游线”双模式。
- 完整地图在同一区域切换，不引起页面大幅跳动。
- 手机端使用全宽游线视图。
- 游线保持到游客主动关闭或生成新游线；“讲这一站”不关闭当前游线。

## 本地资料

项目的知识和运营数据来自 3 份赛题资料：

1. `示范景区公开资料包/灵山胜境 景点结构化数据集.docx`
2. `示范景区公开资料包/灵山胜境：历史、文化、景点特色与个性化游览指南.docx`
3. `示范景区公开资料包/景点景区旅游数据行为分析数据.xlsx`

当前重建结果：

- 3 个来源
- 22 个景点
- 66 个可检索知识分片
- 113 条 FAQ

两份 DOCX 生成问答检索分片；XLSX 作为运营分析样本，不伪装成景点问答分片。管理端把这 3 份资料显示为只读基础资料，运营人员另外新建的文档支持编辑、软删除和重建索引。

## 管理后台

### 运营概览

- 服务人次、问答量、热门问答、满意度与趋势
- 知识文档、数字人版本、反馈处理和质量运行概况
- 运营数据来源标注，不把 XLSX 样本冒充当日真实客流

### 知识库管理

- 显示 3 份本地基础资料、类型、分片数和索引状态
- 新增、编辑、软删除运营维护文档
- 按文档重建索引并记录内容/索引版本
- 资料包原始条目为只读，避免后台误删比赛依据

### 数字人形象

- 只保留一个当前数字人，管理员上传一张有授权的正面形象图即可替换
- 设置中文显示名称、人设和默认声音，并可立即试听
- 点击“保存并应用”后，配置实际影响游客端形象、TTS 和 OpenTalking 驱动
- 后台自动准备并预热 QuickTalk，不向运营人员暴露模型 ID、服务地址或预热术语

单图上传会自动生成可循环的 QuickTalk 驱动素材，适合比赛演示和低门槛维护；口型、表情和人物自然度仍需以最终演示视频和专家评价为准。

### 游客感受度

- 星级与文字反馈
- 情感趋势和关注主题
- 自动服务建议、管理备注和处理状态
- 从“待处理”到“已解决”的管理闭环

### 质量报告

- 固定版本问答集自测
- 准确率、通过数、样本明细、平均/中位/P95 延迟
- 区分“本地自测”与“官方评测”，不把自测冒充赛事结果

## 界面与图像素材

界面以“山水长卷”作为旅游端视觉主线，使用暖纸色、墨蓝和小面积朱砂红；后台保留高密度运营结构，减少重复渐变、玻璃叠卡和强装饰。功能图标使用 Lucide，AI 生成图用于品牌、景区影像和地图基图，不代替交互图标。

当前已接入的新素材：

- `public/assets/generated/hero-lingshan-v2.png`
- `public/assets/generated/app-icon-v2.png`
- `public/assets/generated/route-map-lingshan-v2.png`
- `public/assets/generated/operations-lingshan-v2.png`

其中游线图是无烘焙文字、点位和路径的景区地图基图，站点、线路、中英文标签和当前站点都由前端根据真实游线数据叠加，避免图片内容与交互状态脱节。

## 演示建议

1. 启动项目，确认 3000、8000、8210 都有 HTTP 响应。
2. 打开管理端“景区知识”，展示 3 份只读基础资料和 66 个检索分片。
3. 在“数字人形象”上传一张形象图，试听声音并点击“保存并应用”。
4. 游客端提问“九龙灌浴平日演出时间是什么？”，展示资料依据、中文语音、真实 WebRTC 口型和有效的语速/音量控制。
5. 提问“我喜欢历史文化，帮我规划半日游线”，展示回答摘要和右侧“当前游线”。
6. 点击“讲这一站”，确认游线仍然保留。
7. 提交星级和文字反馈，回到后台展示情感、主题、服务建议和解决闭环。
8. 打开“质量报告”，如实说明本地自测与官方评测的区别。

## 开发与验收命令

```powershell
npm install
npm run startup-audit
npm run typecheck
npm run flow-audit
npm run admin-audit
npm run copy-audit
npm run goal-audit
\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_*.py
npm run build
```

运行中服务检查：

```powershell
npm run live-check
```

一键自检：

```powershell
npm run self-check
```

`npm run self-check` 会生成 `reports/self-check-latest.json`，但它固定使用 mock ASR/TTS，只是 `offline-regression`，不是赛事证据。`npm run live-check` 会生成 `reports/live-service-check-latest.json`，用于真实 Qwen、ASR、TTS 和 OpenTalking 服务检查；单独通过 live-check 仍不等于完成端到端时延验收。

严格赛事验收默认运行 live 模式，并要求浏览器真实语音会话采集的 30 次逐样本 JSON。采集器只在游客页带 `?benchmark=1` 时启用，不增加普通游客页面：

```text
1. 打开 http://127.0.0.1:3000/?benchmark=1，等待数字人预热完成。
2. 在浏览器控制台执行 window.__LINGJING_E2E_BENCHMARK__.clear()。
3. 真人完成 30 次“点麦克风—提问—点麦克风结束”；第 1 次记为 cold，同一页面后续记为 hot。
4. 执行 window.__LINGJING_E2E_BENCHMARK__.getSamples() 检查 30 条，再执行 .download()。
5. 将导出的 JSON 保存为 reports/quality/browser-e2e-samples.json。
```

采集器使用同一个浏览器单调时钟，记录真实 ASR、首段回答、首段 TTS、session 音频入队、`HTMLAudioElement` 实际播放与 WebRTC 嘴部 ROI 变化。权威总时延是 `max(首个有效音频, 首个可见口型) - 录音停止`；各阶段只用于诊断，不相加，避免把并行时间重复计算。mock ASR/TTS、音频播放失败、非 `session_stream` 或缺少嘴部运动的样本会保存为失败样本。

```powershell
$env:COMPETITION_E2E_SAMPLE_FILE="reports/quality/browser-e2e-samples.json"
npm run competition-check

# 等价的显式参数写法
npm run competition-check -- --sample-file reports/quality/browser-e2e-samples.json

# 仅做代码、测试和构建回归；不会产生赛事就绪结论
npm run competition-check:static
```

每个严格样本必须包含 `asr_ms`、`chat_ms`、`tts_ms`、`session_enqueue_ms`、`first_valid_audio_ms`、`first_visible_mouth_ms` 和权威 `end_to_end_ms`。旧 `--first-frame-ms` 兼容参数不会补全严格报告，也不再推荐使用。

生成路径：

- `reports/quality/e2e-latency-latest.json`
- `reports/quality/e2e-latency-latest.md`

真实数字人流式联调证据：

- `reports/quality/opentalking-webrtc-latest.json`
- `reports/quality/opentalking-webrtc-evidence/mouth-before.png`
- `reports/quality/opentalking-webrtc-evidence/mouth-motion-peak.png`

当前报告已通过视频轨、连接、speaking 状态、连续帧变化和可见嘴部运动检查；128 个 speaking 采样帧全部唯一，嘴部帧差平均 `0.9336`、P95 `3.4602`、峰值 `7.5074`。

只有报告中 `measurement_complete=true` 时，才可以根据 `within_target` 判断是否达到本地 5 秒目标。

## 生成数据

重建知识库后会生成：

- `backend/storage/lingjing.db`
- `backend/storage/exports/faq_test_set.json`
- `backend/storage/exports/dashboard_metrics.json`
- `backend/storage/exports/knowledge_manifest.json`

这些文件由资料包生成，不需手工维护。

## 验收边界

- “事实性问答准确率不低于 90%”必须以比赛官方测试集结果为准；当前固定 17 题自测为 100%，与原题零重复的 30 题隐藏本地题集完整自测为 93.33%、请求成功率 100%。两者都不是官方成绩。
- 当前 WebRTC 单链路实测低于 5 秒，但旧端到端报告阶段合计为 `17.74 s` 且 `measurement_complete=false`。“语音问答延迟 <5 秒”必须由 30 次浏览器真实样本证明 `P95 < 5 s`，当前仍待现场实测，不能用其中一个阶段代替端到端结论。
- 当前真实联调证明视频在说话时持续变化且嘴部有可见运动；口型同步、语音和表情自然度的最终结论仍由专家根据演示视频评估。
- 720p/25fps 是 RTX 4060 8GB 演示机的项目配置，不是对所有负载的通用承诺。
- 远程 FlashTalk/FlashHead 仅保留接口，尚未经部署和质量/延迟验收，不应宣称为已完整集成。
