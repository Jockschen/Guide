# OpenTalking 参考映射说明

本文用于答辩和代码评审说明：本项目参考 [datascale-ai/opentalking](https://github.com/datascale-ai/opentalking) 的实时数字人会话思路。当前比赛主链路采用 **Edge 中文语音 → OpenTalking 官方 session → QuickTalk → WebRTC 720×720/25fps**，把游客输入、知识库问答、真实音频、OpenTalking 视频口型、字幕和说话状态串成可在 Windows 上演示的完整链路。

## 参考原则

- 先保证导览主链路可用，再替换更强的外部模型或数字人服务。
- 游客端只展示自然交互控件，不展示模型、Provider、接口地址等技术字眼。
- 管理端只保留运营大屏、资料库和问答洞察；模型、语音和 OpenTalking 地址通过 `.env` 与部署说明配置。
- 景区事实内容只来自示范景区资料包和后台上传资料，不用界面素材或模型想象补充核心资料。

## 架构映射

| OpenTalking 思路 | 本项目实现 | 对应价值 |
| --- | --- | --- |
| 前端会话承接游客输入、字幕和播放状态 | `components/TouristExperience.tsx` 统一处理文本、语音、图片、实时画面截帧、回答渲染和满意度反馈 | 游客像和真人导游聊天一样完成问答 |
| STT 作为可替换模块 | `components/TouristExperience.tsx` 优先生成 16k/16bit 单声道语音，`backend/server/voice.py` 提供 `funasr`、`sherpa_onnx`、`vivo`、`mock` 适配 | 赛事验收必须使用非 mock 识别；mock 只用于离线回归 |
| LLM 接收用户问题和上下文 | `/api/chat` 结合 Qwen 与本地知识库检索结果生成导游回答 | 多模态大模型负责理解，资料包负责事实边界 |
| TTS 作为可替换模块 | `backend/server/voice.py` 当前默认 Edge，并保留 `cosyvoice`、`piper`、`sherpa_onnx`、`vivo`、`mock` 适配 | Edge 生成真实 PCM WAV；mock 或空音频不能用于口型验收 |
| 字幕和数字人状态随语音播放同步 | 音频优先：页面预先建立官方 session，Edge 音频就绪后上传同一会话，浏览器从 WebRTC 持续音视频轨呈现 speaking 与字幕状态 | 避免等待整段 MP4；同一会话可连续讲解和打断 |
| 可桥接更强的数字人后端 | `.env` 中的 `OPENTALKING_BASE_URL` 和 official session 配置承接 QuickTalk；`OPENTALKING_LIPSYNC_PATH`、`OPENTALKING_INFER_COMMAND` 仅保留旧桥接兼容 | 当前主线是 session/WebRTC，旧整段 MP4 不是实时验收依据 |
| 离线回归与赛事证据分离 | `MOCK_ASR_TEXT`、mock TTS、`npm run self-check` 仅用于 offline-regression | `self-check` 明确 `competition_evidence=false`，不能作为评审现场真实能力证据 |
| 管理端观察运营效果 | `components/AdminConsole.tsx` 的运营大屏、资料库和问答洞察 | 管理方能看到数据口径、游客问题、感受趋势和服务量 |

## 真实驱动边界

OpenTalking 的真实数字人效果来自可替换模型后端和音视频播放链路。当前验收主线要求本机 QuickTalk 形象与模型已准备、official session worker 已预热，并由浏览器实际收到 WebRTC 音视频轨；静态海报、CSS 动画或旧 MP4 文件不能替代这项证据。部署需要准备：

1. OpenTalking official session 服务；`server.opentalking_bridge` 只保留兼容桥接。
2. 当前已验收的 QuickTalk 模型、形象资产及其权重。
3. 合规授权的数字人照片或视频素材。
4. 可被服务端访问的语音文件或音频流。
5. `.env` 中的 `OPENTALKING_BASE_URL`、`OPENTALKING_LIPSYNC_PATH`、`OPENTALKING_AVATAR_IMAGE` 和 `OPENTALKING_INFER_COMMAND`。

项目提供两个命令：

```powershell
npm run opentalking:setup
npm run opentalking:start
```

`setup` 会下载 OpenTalking 仓库和常用 QuickTalk/Wav2Lip 权重；`start` 会启动本地服务。official session 是当前主链路；`OPENTALKING_INFER_COMMAND` 指定的旧桥接推理仍可生成 MP4，但只作为兼容兜底。

### 音频优先与短段真实口型

游客体验以音频优先为边界：页面先连接 official session，Edge TTS 音频准备后直接上传同一会话，QuickTalk worker 驱动 WebRTC 持续画面、speaking 状态与可见口型。旧 `legacy_mp4` 仍保留“短段真实口型视频、柔和切入”兼容逻辑，但只作兜底，不属于当前实时主链路证据。

QuickTalk 当前验收档由 `.env` 控制：`OPENTALKING_SESSION_TARGET_FPS=25`、`OPENTALKING_SESSION_TARGET_RESOLUTION=720x720`、`OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE=720`、`OPENTALKING_QUICKTALK_X264_PRESET=fast`、`OPENTALKING_QUICKTALK_X264_CRF=18`。该档位配合 worker cache、形象预热和官方 session，目标是 720×720/25fps 持续流；它是当前演示机配置，不是对任意负载的通用帧率保证。部署依据见 [QuickTalk local](https://datascale-ai.github.io/opentalking/latest/en/avatar_models/deployment/quicktalk-local/) 与 [Windows deployment](https://datascale-ai.github.io/opentalking/latest/en/quick-start/windows-deployment/)。

## 游客端体验取舍

游客端默认不是功能展示墙，而是一个导游对话界面：

1. 普通问答只显示数字人、聊天、字幕和快捷问题。
2. 用户问到“路线、规划、亲子、历史、自然”等意图时，才在回答下展开路线卡片。
3. 路线卡片的节点可悬停和点击，继续追问该景点怎么玩。
4. 图片上传用于看图问景点，实时视频采用按需截帧，避免持续上传造成延迟和隐私压力。
5. 真实讲解画面只作为无中断的增强层出现，游客不会看到模型加载、口型生成或链路异常等工程状态。

## 后台体验取舍

后台只保留比赛需要的运营闭环：

1. 运营大屏：展示当前游客、问答次数、知识片段、评分、趋势、感受分布和热门景点。
2. 资料库：上传 Word/Excel、同步示范资料包，查看景点、知识片段和 FAQ。
3. 问答洞察：按日期、景点和关键词筛选日志，按高频词进入问题板块，查看 Markdown 问答详情。

## 与赛题要求的对应关系

| 赛题要求 | 本项目落点 |
| --- | --- |
| 多模态交互 | 文本、语音、图片上传、实时画面截帧 |
| 智能问答与讲解 | Qwen + 本地知识库检索 + Markdown 回答渲染 |
| 个性化推荐 | 根据亲子、历史、自然、半日游等意图生成路线卡片 |
| 语音、表情和口型同步 | Edge 真实音频上传 OpenTalking official session，QuickTalk 通过 WebRTC 输出持续画面、speaking 状态和可见口型；旧 MP4 仅兜底 |
| 知识库管理 | 后台资料同步、知识片段、FAQ 测试集、资料来源 |
| 数字人形象管理 | 游客端支持形象图片、形象视频和实时视频；真实口型通过 OpenTalking 桥接服务接入 |
| 游客感受度报告 | 满意度反馈、问答日志、热门问题、服务建议 |
| 数据大屏概览 | 基于资料包 Excel 生成趋势、客群和热门指标 |

## 验收方式

推荐答辩前使用浏览器/真实会话采集的 30 次样本运行默认 strict live 验收：

```powershell
$env:COMPETITION_E2E_SAMPLE_FILE="reports/quality/browser-e2e-samples.json"
npm run competition-check

# 仅做离线静态回归，不构成赛事证据
npm run competition-check:static
npm run self-check
```

`competition-check` 默认运行 strict live：除类型、测试和构建外，还要求非 mock ASR/TTS、真实 ASR WAV 回环、OpenTalking WebRTC 六项检查，以及 30 次完整样本成功率 100%、P95 <5 秒。当前旧端到端报告为 `17.74 s` 且 `measurement_complete=false`，新的 30 次现场报告尚未完成。`self-check` 固定使用 mock，只是离线回归。报告写入：

```text
reports/competition-check-latest.json
```

固定 17 题 `17/17 = 100%`、独立隐藏 30 题完整自测 `28/30 = 93.33%` 且请求成功率 `100%`，仍都只是本地自测，不是比赛官方测试集成绩。只有真实语音或 OpenTalking 服务未连接时，游客端可以降级保证可用，但降级结果不能作为赛事能力通过证据。
