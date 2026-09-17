# 开源方案调研与落地决策

更新日期：2026-07-12

本项目的目标不是拼接一段离线 MP4，而是在 RTX 4060 8GB 的 Windows 电脑上实现可重复演示的实时导览链路：景区知识问答生成文本，中文语音合成输出音频，数字人通过 WebRTC 连续播放并在收到音频后产生口型与微动作。所有性能和准确率结论均以本机报告为准，不以仓库宣传值替代实测。

## 已采用的开源能力

| 能力 | 开源项目 | 借鉴内容 | 本项目落地 |
| --- | --- | --- | --- |
| 数字人实时会话 | [datascale-ai/opentalking](https://github.com/datascale-ai/opentalking) | session 生命周期、音频入队、WebRTC 音视频轨、QuickTalk 本地驱动 | 主链路固定为 `session + WebRTC + QuickTalk`；720p、25fps；启动时预热模型和当前单一形象 |
| 中文神经语音 | [rany2/edge-tts](https://github.com/rany2/edge-tts) | 无需密钥的在线神经语音；支持 voice、rate、volume | 默认温和女声 `zh-CN-XiaoxiaoNeural`；语速和音量同时传入后端，并实时作用于浏览器播放 |
| 离线语音扩展 | [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Windows 本地 ASR/TTS、中文模型、ONNX 推理 | 作为无网环境的后续替换接口保留，不与 QuickTalk 争用当前 8GB 显存预算 |
| 问答质量评测 | [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) | 固定评测集、事实与上下文对齐、失败样本分析 | 使用版本冻结的 17 题景区问答集；逐题记录必含事实、资料来源和耗时；页面公开计算公式与失败题 |

## 取舍结论

### 首选：OpenTalking QuickTalk 流式链路

- 游客页面加载后创建官方 session，并等待 `worker_ready` 再交换 WebRTC offer，避免模型尚未就绪时只得到空轨道。
- TTS 生成 PCM WAV 后直接上传至当前 session，数字人画面持续存在；静态头像仅在实时轨尚未可播放时显示，因此不会叠成两个人像。
- 当前单图形象会被处理成带自然轻微位移和眨眼的 25fps 模板；管理员重新上传一张图片后，系统重新生成并预热同一个当前形象。
- 真实验收必须同时满足：会话就绪、收到视频轨、上传音频成功、会话进入讲解状态、讲解前后帧差显著大于空闲噪声。

### 语音：Edge TTS 为默认，离线方案可替换

Edge TTS 已存在于 OpenTalking 的本地 Python 环境，不额外占用 GPU；它提供自然中文音色，并原生接收语速、音量参数。前端仍同步设置 `HTMLAudioElement.playbackRate` 与 `volume`，所以用户拖动控制项后，当前播放与后续合成都能立即生效。

若比赛现场必须完全离线，可把同一 `TTS_PROVIDER` 接口切换到 sherpa-onnx 或其他本地中文 TTS；切换前应重新记录音质、首包延迟和显存占用，不在没有实测时宣称等效。

### 不采用：整段 MP4 作为主链路

整段生成会把“等待完整视频”的时间暴露给游客，且无法稳定满足语音问答小于 5 秒的交互目标。旧 MP4 接口仅保留为兼容层或录制素材工具，不再作为游客端优先路径。

### 暂不在 8GB 本机承诺 MuseTalk

[TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk) 仍可作为远程高质量后端候选；本项目后台保留驱动提供方扩展点，也可进一步接 OpenTalking 的 FlashTalk/FlashHead。任何切换都必须先通过相同的 WebRTC 帧变化、端到端延迟和显存稳定性测试。

## 可审计证据

- 冻结问答报告：`reports/quality/frozen-qa-latest.json` 与 `.md`
- 数字人端到端报告：`reports/quality/e2e-latency-latest.json`
- 启动与在线检查：`reports/startup-audit-latest.json`、`reports/live-service-check-latest.json`
- 比赛要求逐项状态：`docs/competition-requirements-audit.md`

报告只代表记录时的本机环境与版本。比赛官方准确率、专家自然度评价和现场网络条件仍需独立验收。
