# 数字人驱动优化设计

日期：2026-07-07

## 目标

本轮只优化数字人。现有项目已经有 OpenTalking 兼容桥接、TTS、2D 舞台和演示片段兜底，本轮不新增不可控的大模型下载链路，而是把数字人驱动状态做成可验证的产品能力：后端明确判定真实视频、演示片段、2D 音频驱动三种模式，前端按判定结果展示稳定状态，并把验收脚本覆盖到这个决策层。

## 开源参考

- datascale-ai/opentalking：参考其“会话编排 + 数字人播放 + 可替换模型后端”的产品管线，保留本项目的桥接适配层。
- TMElyralab/MuseTalk、Rudrabha/Wav2Lip：参考音频驱动口型同步的输入输出边界，不在主项目中绑定权重。
- OpenTalker/SadTalker、OpenTalker/video-retalking、KwaiVGI/LivePortrait、GuijiAI/duix.ai：作为后续可替换后端候选，当前只吸收“明确驱动来源与兜底边界”的工程约束。

完整调研写入 `docs/digital-human-open-source-research.md`。

## 方案

后端新增数字人驱动决策元数据，随 `/api/avatar/lipsync`、`/api/admin/pipeline-check`、`/api/admin/demo-readiness` 返回。元数据包含驱动模式、可声明类型、展示标签、是否可播放视频、是否需要外部模型服务、兜底原因和验收标签。这样真实视频与演示片段不会混成一个状态，2D 舞台也不再只是隐式 fallback。

前端 `TouristExperience` 保存最近一次驱动元数据，并传给 `DigitalHuman`。`DigitalHuman` 在头像状态区域显示简洁标签，例如“实时口型”“演示片段”“音频驱动”，避免游客端暴露技术 provider 名称。播放逻辑调整为：不在 TTS 开始前抢先播放演示片段；只有 lipsync 接口明确返回演示或真实视频时才切到视频层。

验收层补充后端单元测试和静态审计：测试 OpenTalking、demo、2D fallback 三种驱动元数据；审计前端包含 driver metadata 的消费点；目标验收命令仍是 `npm run goal-audit`、后端测试、`npm run typecheck`、`npm run build`，必要时运行 `npm run self-check`。

## 非目标

- 不下载或安装大型模型权重。
- 不把预生成 demo 伪装成实时口型。
- 不在游客端展示 ASR/TTS/OpenTalking 等技术调试名。
