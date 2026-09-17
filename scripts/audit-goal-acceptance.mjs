import { readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();

function read(relativePath) {
  return readFileSync(path.join(root, relativePath), "utf-8");
}

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

function assertIncludes(source, snippets, label) {
  for (const snippet of snippets) {
    assert(source.includes(snippet), `${label} 缺少：${snippet}`);
  }
}

const envExample = read(".env.example");
const packageJson = JSON.parse(read("package.json"));
const config = read("backend/server/config.py");
const voice = read("backend/server/voice.py");
const avatar = read("backend/server/avatar.py");
const opentalkingBridge = read("backend/server/opentalking_bridge.py");
const qwenClient = read("backend/server/qwen_client.py");
const main = read("backend/server/main.py");
const schemas = read("backend/server/schemas.py");
const types = read("lib/types.ts");
const apiClient = read("lib/api.ts");
const tourist = read("components/TouristExperience.tsx");
const itinerary = read("components/ItineraryPanel.tsx");
const digitalHuman = read("components/DigitalHuman.tsx");
const admin = read("components/AdminConsole.tsx");
const competitionPanels = read("components/admin/CompetitionPanels.tsx");
const miniCharts = read("components/MiniCharts.tsx");
const css = read("app/globals.css");
const readme = read("README.md");
const mapDoc = read("docs/opentalking-architecture-map.md");
const demoRunbook = read("docs/demo-runbook.md");
const flowAudit = read("scripts/audit-tourist-flow.mjs");
const copyAudit = read("scripts/audit-tourist-copy.mjs");
const selfCheck = read("scripts/self-check.mjs");
const liveCheck = read("scripts/live-service-check.mjs");
const competitionCheck = read("scripts/competition-check.mjs");
const wav2lipRenderer = read("scripts/opentalking_wav2lip_gpu_render.py");
const quicktalkRenderer = read("scripts/opentalking_quicktalk_gpu_render.py");
const quicktalkPrepare = read("scripts/prepare_quicktalk_avatar_asset.py");
const motionVerifier = read("scripts/verify_lipsync_motion.py");
const opentalkingAssetCheck = read("scripts/check-opentalking-assets.ps1");
const voiceTests = read("backend/tests/test_voice.py");
const avatarTests = read("backend/tests/test_avatar.py");
const qwenTests = read("backend/tests/test_qwen_client.py");
const pipelineTests = read("backend/tests/test_pipeline.py");
const opentalkingScriptTests = read("backend/tests/test_opentalking_scripts.py");

assertIncludes(envExample, [
  "ASR_PROVIDER=funasr",
  "TTS_PROVIDER=edge",
  "FUNASR_BASE_URL=",
  "COSYVOICE_BASE_URL=",
  "SHERPA_ONNX_ASR_COMMAND=",
  "SHERPA_ONNX_TTS_COMMAND=",
  "PIPER_EXE=",
  "PIPER_MODEL=",
  "VIVO_APP_KEY=",
  "OPENTALKING_BASE_URL=",
  "OPENTALKING_RESULT_PATH=",
  "OPENTALKING_MODEL=quicktalk",
  "OPENTALKING_AVATAR_IMAGE=",
  "OPENTALKING_AVATAR_DIR=",
  "OPENTALKING_QUICKTALK_ASSET_ROOT=models/quicktalk",
  "OPENTALKING_QUICKTALK_DEVICE=cuda:0",
  "OPENTALKING_QUICKTALK_MAX_SECONDS=0",
  "OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE=720",
  "OPENTALKING_QUICKTALK_X264_PRESET=fast",
  "OPENTALKING_QUICKTALK_X264_CRF=18",
  "OPENTALKING_WAV2LIP_DEVICE=cuda",
  "OPENTALKING_WAV2LIP_FACE_DET_DEVICE=cuda",
  "OPENTALKING_WAV2LIP_MODEL_ROOT=models/wav2lip",
  "OPENTALKING_WAV2LIP_MAX_SECONDS=0",
  "OPENTALKING_INFER_COMMAND=",
  "opentalking_quicktalk_gpu_render.py",
  '--avatar-dir "{avatar}"',
  "OPENTALKING_DEMO_VIDEO=",
  "OPENTALKING_DEMO_FALLBACK=0",
  "VIVO_TTS_VOICE_STORY=",
  "VIVO_TTS_VOICE_BROADCAST=",
  "VIVO_TTS_ENGINE_STORY=",
  "VIVO_TTS_ENGINE_BROADCAST=",
  "MOCK_ASR_TEXT="
], ".env.example");
assert(!/Audio2Face/.test(envExample), ".env.example 不应引导 Audio2Face 路线。");

assertIncludes(config, [
  'os.getenv("ASR_PROVIDER", "funasr")',
  'os.getenv("TTS_PROVIDER", "cosyvoice")',
  "mock_asr_text",
  "sherpa_onnx_asr_command",
  "sherpa_onnx_tts_command",
  "piper_exe",
  "piper_model",
  "opentalking_result_path",
  "opentalking_avatar_image",
  "opentalking_model"
], "backend/server/config.py");

assertIncludes(voice, [
  'ASR_PROVIDERS = {"funasr", "sherpa_onnx", "vivo", "mock"}',
  'TTS_PROVIDERS = {"edge", "cosyvoice", "piper", "sherpa_onnx", "vivo", "mock"}',
  "def speech_runtime_status",
  "def normalize_spoken_text",
  "def synthesize_tts",
  "def transcribe_asr",
  "def _mock_tts",
  "def _mock_asr",
  "def _edge_tts",
  "def _piper_tts",
  "def _sherpa_onnx_asr_local",
  "def _sherpa_onnx_tts_local",
  "def synthesize_vivo_tts",
  "def transcribe_vivo_asr",
  "def _provider_voice",
  "def _provider_voice_config",
  "def _split_tts_chunks",
  "VIVO_TTS_VOICE_",
  "VIVO_TTS_ENGINE_",
  "estimate_visemes(text)"
], "backend/server/voice.py");

assertIncludes(main, [
  '@app.post("/api/chat")',
  '@app.post("/api/route-plan")',
  '@app.post("/api/admin/sources/upload")',
  '@app.get("/api/admin/log-summary")',
  '@app.delete("/api/admin/logs/{log_id}")',
  '@app.get("/api/admin/pipeline-check")',
  '@app.get("/api/admin/demo-readiness")',
  '@app.post("/api/tts/synthesize")',
  '@app.post("/api/asr/transcribe")',
  '@app.post("/api/avatar/lipsync")',
  "retrieve(question, limit=3)",
  "call_qwen(",
  "synthesize_tts(",
  "transcribe_asr("
], "backend/server/main.py");

assertIncludes(schemas, [
  "class TTSRequest",
  "allow_demo: bool",
  "voice: str",
  "style: str",
  "speed: float",
  "volume: float",
  "guide_style: str",
  "voice_preset: str"
], "backend/server/schemas.py");

assertIncludes(avatar, [
  "request_lipsync",
  "opentalking_base_url",
  "_normalize_opentalking_result",
  "_poll_task",
  "video_url",
  "video_base64",
  "task_id",
  "demo_video_status",
  "opentalking-demo",
  "allow_demo",
  "build_driver_metadata",
  "claim_real_lipsync",
  "fallback_viseme_timeline",
  "estimate_visemes",
  '"2d-fallback"'
], "backend/server/avatar.py");

assertIncludes(main, [
  "avatar_driver",
  "digital_human_driver_mode",
  "build_driver_metadata"
], "backend/server/main.py");

assertIncludes(types, [
  "export type DigitalHumanDriver",
  "mode: \"real_video\" | \"demo_video\" | \"audio_2d\"",
  "claim_real_lipsync",
  "acceptance"
], "lib/types.ts");

assertIncludes(apiClient, [
  "unwrapApiPayload",
  '"data" in maybeEnvelope',
  "return payload as T"
], "lib/api.ts");

assertIncludes(opentalkingBridge, [
  '"/api/lipsync"',
  "OPENTALKING_INFER_COMMAND",
  "{audio}",
  "{image}",
  "{avatar}",
  "{output}",
  "video_url",
  "taskkill",
  "render_log_dir"
], "backend/server/opentalking_bridge.py");

assertIncludes(qwenClient, [
  "sanitize_markdown_answer",
  "不要输出 HTML",
  "<details>",
  "re.sub"
], "backend/server/qwen_client.py");

assertIncludes(tourist, [
  "/api/chat",
  "/api/asr/transcribe",
  "/api/tts/synthesize",
  "/api/avatar/lipsync",
  "voice: voicePreset",
  "style: guideStyle",
  "speed: speechRate",
  "volume: speechVolume",
  "normalizeSpeechText",
  "normalizeAssistantMarkdown",
  "formatClockTime",
  "subtitlesEnabled",
  "driverVideoUrl",
  "driverVideoRef",
  "speechRunIdRef",
  "apiGet<Health>(\"/api/health\")",
  "driverPending",
  "syntheticMotionEnabled",
  "allow_demo: false",
  "splitNarrationSegments",
  "requestNarrationAudio",
  "void prepareDriverVideo",
  "blendDriverVideo",
  "playAudioWithMouth",
  "GUIDE_STATUS",
  "presentationStatus",
  "statusLabel={presentationStatus}",
  "subtitlesEnabled ? subtitle : null",
  "avatarDriver",
  "setAvatarDriver",
  "lipsync.driver",
  "video_url",
  "handleQuestionImage",
  "captureCameraFrame",
  "shouldUpdateRoute",
  "ItineraryPanel",
  "ItinerarySummary",
  "activeRoutePlan",
  "toggleSpeechPlayback",
  "stopSpeechPlayback",
  "finishSpeechPlayback",
  "StarFeedback",
  "FollowUpSuggestions",
  "feedbackRatings",
  "buildFollowUpSuggestions",
  "starterSuggestions",
  "guide_style: guideStyle",
  "voice_preset: voicePreset",
  "story",
  "broadcast",
  "encodePcm16",
  "question.pcm",
  "ReactMarkdown"
], "components/TouristExperience.tsx");

assertIncludes(itinerary, [
  "itinerary-panel",
  "itinerary-map",
  "route-map-lingshan-v2.png",
  "route-track",
  "map-stop",
  "current-stop",
  "itinerary-stops",
  "onNarrateStop",
  "onReplace"
], "components/ItineraryPanel.tsx");
assert(!tourist.includes("opentalkingReady || demoReady"), "游客端不应把 demo fallback 当作真实 OpenTalking 嘴型。");
assert(!tourist.includes("quick-action-row"), "游客端不应保留顶部快捷动作按钮行。");
for (const retiredVisitorCopy of ["生成口型中", "正在生成口型视频", "同步口型讲解", "口型链路异常", "口型视频生成失败", "讲解准备中", "正在为你讲解", "正在整理资料", "正在查找本地资料", "正在整理景区问答", "正在为你准备讲解", "正在播报", "正在识别", "管理中心"]) {
  assert(!tourist.includes(retiredVisitorCopy), `游客端不应暴露技术文案：${retiredVisitorCopy}`);
}

assertIncludes(digitalHuman, [
  "GuideStatus",
  "avatar-stage",
  "avatar-presentation",
  "scenic-signature",
  "avatar-media-frame",
  "avatar-portrait",
  "expression-${expression}",
  "data-expression={expression}",
  'aria-live="polite"',
  'aria-atomic="true"',
  "subtitle !== null",
  "driverVideoUrl",
  "driverPending",
  "数字人讲解画面",
  "数字人实时讲解画面",
  "avatar-video-driver",
  "avatar-stream",
  "streamVisible",
  "driverVideoReady",
  "导游在线"
], "components/DigitalHuman.tsx");
assert(!digitalHuman.includes("loop"), "真实 OpenTalking 视频不应循环播放。");
assert(!digitalHuman.includes("avatar-driver-chip") && !digitalHuman.includes("avatar-driver-layer"), "数字人不应保留重复驱动状态浮层。");

assertIncludes(css, [
  ".avatar-stage",
  ".avatar-presentation",
  ".scenic-signature",
  ".avatar-media-frame",
  ".avatar-portrait",
  ".subtitle-panel",
  ".expression-friendly",
  ".expression-listening",
  ".expression-thinking",
  ".expression-speaking",
  ".tourist-shell .avatar-video-driver.is-ready",
  "object-fit: cover",
  ".itinerary-panel",
  ".itinerary-map",
  ".route-track-line",
  ".map-stop",
  ".current-stop",
  ".keyword-cloud",
  ".experience-controls",
  "grid-template-columns: repeat(4, 1fr)",
  ".admin-shell.navigation-open .admin-sidebar",
  "@keyframes gentle-pulse"
], "app/globals.css");
assert(!digitalHuman.includes("avatar-lip-sync") && !digitalHuman.includes("avatar-eye-shade"), "数字人不应保留伪口型或眉毛贴片。");

assertIncludes(admin, [
  '"overview"',
  '"knowledge"',
  '"digital-human"',
  '"feedback"',
  '"quality"',
  "运营概览",
  "知识内容",
  "数字人形象",
  "游客感受",
  "质量报告",
  "apiUpload",
  "/api/admin/competition/overview",
  "/api/admin/competition/feedback",
  "/api/admin/competition/quality-runs",
  "navigation-open",
  "mobile-nav-button",
  "admin-tabs"
], "components/AdminConsole.tsx");

assertIncludes(competitionPanels, [
  "OverviewPanel",
  "KnowledgePanel",
  "DigitalHumanPanel",
  "FeedbackPanel",
  "QualityPanel",
  "今日运营脉搏",
  "平均满意度",
  "问答依据",
  "上传形象照片",
  "情感趋势",
  "服务建议",
  "本地自测",
  'className="quality-method-steps"',
  "<b>题集</b>",
  "<b>判定</b>",
  "<b>结果用途</b>"
], "components/admin/CompetitionPanels.tsx");
assert(!competitionPanels.includes('<details className="quality-method"'), "自测方法仍是展开式大卡。");

assertIncludes(miniCharts, [
  "line-trend",
  "trend-grid-line",
  "line-trend-summary",
  "formatDateLabel",
  "formatShortDateLabel",
  "onChoose?.(label)",
  "role=\"button\"",
  "暂无日期数据"
], "components/MiniCharts.tsx");

assertIncludes(css, [
  ".admin-shell",
  ".admin-sidebar",
  ".admin-tabs",
  ".admin-main",
  ".admin-header",
  ".metric-ribbon",
  ".feedback-layout",
  ".quality-verdict",
  ".quality-method-steps",
  ".floating-rocket",
  ".star-feedback",
  ".follow-up-suggestions",
  ".line-trend",
  ".line-trend-summary",
  ".admin-shell.navigation-open .admin-sidebar"
], "app/globals.css");

assertIncludes(wav2lipRenderer, [
  "Wav2LipAdapter",
  "_resample_pcm_i16",
  "target_sample_rate: int = 16000",
  "adapter.load_model(args.device)",
  "adapter.extract_features_for_stream",
  "adapter.infer(features, avatar_state)",
  "compose_frame",
  "ffmpeg mux"
], "scripts/opentalking_wav2lip_gpu_render.py");
assertIncludes(wav2lipRenderer, [
  'OPENTALKING_WAV2LIP_MAX_SECONDS", "0"',
  "_pad_frames_to_audio",
  "_wav_duration_seconds"
], "scripts/opentalking_wav2lip_gpu_render.py");
assert(!wav2lipRenderer.includes("OWoman.mp4"), "Wav2Lip 渲染脚本不应依赖 OpenTalking 示例视频。");

assertIncludes(quicktalkRenderer, [
  "QuickTalkAdapter",
  "adapter.load_model(args.device)",
  "adapter.load_avatar(str(avatar_dir))",
  "adapter.extract_features_for_stream",
  "adapter.infer(features, avatar_state)",
  'OPENTALKING_QUICKTALK_MAX_SECONDS", "0"',
  "OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE",
  "OPENTALKING_QUICKTALK_X264_PRESET",
  "-movflags",
  "_pad_frames_to_audio",
  "_wav_duration_seconds",
  '"model": "quicktalk"'
], "scripts/opentalking_quicktalk_gpu_render.py");

assertIncludes(quicktalkPrepare, [
  "template_",
  "template_video",
  "model_type",
  "quicktalk",
  "_write_template_video"
], "scripts/prepare_quicktalk_avatar_asset.py");

assertIncludes(motionVerifier, [
  "mouth_mean_delta",
  "mouth_max_delta",
  "moving_pairs",
  "manifest.json",
  "mouth_center"
], "scripts/verify_lipsync_motion.py");

assertIncludes(opentalkingAssetCheck, [
  "lingjing-guide-quicktalk\\manifest.json",
  "lingjing-guide-quicktalk\\quicktalk\\template_720x720.mp4",
  "models\\wav2lip\\wav2lip384.pth",
  "models\\wav2lip\\s3fd.pth",
  "lingjing-guide-wav2lip\\manifest.json",
  "lingjing-guide-wav2lip\\reference.png",
  "Lingjing QuickTalk/Wav2Lip avatar assets"
], "scripts/check-opentalking-assets.ps1");

assertIncludes(readme, [
  "qwen3.5-omni-plus-2026-03-15",
  "ASR_PROVIDER",
  "TTS_PROVIDER",
  "默认使用 Edge 中文神经网络语音",
  "FunASR、CosyVoice",
  "Piper",
  "sherpa-onnx",
  "npm run opentalking:setup",
  "OPENTALKING_SESSION_ENABLED=1",
  "OpenTalking QuickTalk 官方 session + WebRTC",
  "只有真实 WebRTC 或真实视频结果可以标记为真实口型",
  "个性化推荐游线",
  "赛题要求验收矩阵",
  "npm run live-check",
  "npm run self-check",
  "720p/25fps 是 RTX 4060 8GB 演示机的项目配置"
], "README.md");

assertIncludes(mapDoc, [
  "datascale-ai/opentalking",
  "OpenTalking 视频口型",
  "16k/16bit 单声道语音",
  "TTS 作为可替换模块",
  "字幕和数字人状态随语音播放同步",
  "音频优先",
  "短段真实口型视频",
  "柔和切入",
  "OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE",
  "OPENTALKING_QUICKTALK_X264_PRESET",
  "真实驱动边界",
  "OPENTALKING_INFER_COMMAND",
  "npm run opentalking:setup",
  "与赛题要求的对应关系"
], "docs/opentalking-architecture-map.md");

assertIncludes(demoRunbook, [
  "7 分钟演示脚本",
  "Edge 中文神经网络语音",
  "上传到 OpenTalking 实时驱动",
  "个性化推荐游线",
  "服务人次、热门问答、满意度和服务趋势",
  "npm run live-check"
], "docs/demo-runbook.md");

assertIncludes(demoRunbook, [
  "字幕位于数字人媒体框下方",
  "手机端字幕仍然可见",
  "导游在线 → 正在聆听 → 正在整理 → 正在讲解",
  "状态反馈不代替真实口型",
  "减少动态效果"
], "docs/demo-runbook.md");

assertIncludes(liveCheck, [
  "LIVE_CHECK_STRICT",
  "/api/admin/demo-readiness",
  "/api/asr/transcribe",
  "audio/pcm",
  "resamplePcm16Mono",
  "qwen_configured",
  "asr_effective_provider",
  "asr_provider",
  "asr_text_ready",
  "tts_effective_provider",
  "opentalking_ready",
  "demo_video_ready",
  "competition_ready",
  "pipeline_avatar_provider",
  "tts_audio_ready",
  "readinessData.blockers",
  "live-service-check-latest.json"
], "scripts/live-service-check.mjs");
assertIncludes(competitionCheck, [
  "COMPETITION_E2E_SAMPLE_FILE",
  "--sample-file",
  "buildE2EBenchmarkArgs",
  "competition-strict"
], "scripts/competition-check.mjs");

assertIncludes(flowAudit, [
  "startBackendRecording()",
  "encodePcm16",
  "question.pcm",
  "voice: voicePreset",
  "style: guideStyle",
  "speed: speechRate",
  "volume: speechVolume",
  "normalizeSpeechText"
], "scripts/audit-tourist-flow.mjs");
assertIncludes(copyAudit, [
  "游客端可见文案包含技术细节",
  "ASR",
  "TTS",
  "Provider",
  "API Key"
], "scripts/audit-tourist-copy.mjs");
assertIncludes(selfCheck, [
  'mode: "offline-regression"',
  "competition_evidence: false",
  "导游在线",
  "正在聆听",
  "正在整理",
  "正在讲解",
  "讲解已暂停",
  "生成口型中",
  "同步口型讲解",
  "口型链路异常",
  "管理中心"
], "scripts/self-check.mjs");

assertIncludes(voiceTests, [
  "test_vivo_asr_uses_pcm_recording_when_key_is_configured",
  "test_sherpa_onnx_asr_command_template_returns_text",
  "test_sherpa_onnx_tts_command_template_writes_audio",
  "test_normalize_spoken_text_reads_clock_times_naturally",
  "test_vivo_voice_presets_map_to_documented_speakers",
  "test_vivo_tts_chunks_long_text_under_request_limit",
  "test_default_tts_falls_back_when_cosyvoice_is_not_ready",
  "test_default_asr_falls_back_when_funasr_is_not_ready"
], "backend/tests/test_voice.py");
assertIncludes(qwenTests, [
  "test_sanitize_markdown_answer_removes_html_details",
  "sanitize_markdown_answer",
  "<details>"
], "backend/tests/test_qwen_client.py");
assertIncludes(avatarTests, [
  "test_opentalking_video_base64_becomes_static_video",
  "test_opentalking_task_result_is_polled",
  "test_demo_video_status_maps_storage_file_to_static_url",
  "test_demo_video_is_explicit_fallback_only",
  "video_url"
], "backend/tests/test_avatar.py");
assertIncludes(pipelineTests, [
  "test_pipeline_check_covers_knowledge_tts_and_lipsync",
  "test_demo_readiness_exposes_competition_blockers",
  "retrieved_chunks",
  "visemes_count",
  "tts_audio_ready"
], "backend/tests/test_pipeline.py");
assertIncludes(voiceTests, [
  "test_edge_tts_generates_pcm_wav_with_real_rate_and_volume_controls",
  'self.assertEqual(result["provider"], "edge")',
  'self.assertTrue(str(result["audio_url"]).endswith("edge.wav"))'
], "backend/tests/test_voice.py");
assertIncludes(opentalkingScriptTests, [
  "test_wav2lip_renderer_uses_real_opentalking_adapter",
  "test_motion_verifier_checks_mouth_roi"
], "backend/tests/test_opentalking_scripts.py");

assert(packageJson.scripts["copy-audit"] === "node scripts/audit-tourist-copy.mjs", "package.json 缺少 copy-audit。");
assert(packageJson.scripts["flow-audit"] === "node scripts/audit-tourist-flow.mjs", "package.json 缺少 flow-audit。");
assert(packageJson.scripts["self-check"] === "node scripts/self-check.mjs", "package.json 缺少 self-check。");
assert(packageJson.scripts["live-check"] === "node scripts/live-service-check.mjs", "package.json 缺少 live-check。");
assert(packageJson.scripts["competition-check"] === "node scripts/competition-check.mjs --live", "package.json 的 competition-check 必须默认运行 live strict 验收。");
assert(packageJson.scripts["competition-check:static"] === "node scripts/competition-check.mjs --static", "package.json 缺少显式 competition-check:static。");
assert(packageJson.scripts["opentalking:setup"] === "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-opentalking.ps1", "package.json 缺少 opentalking:setup。");
assert(packageJson.scripts["opentalking:start"] === "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-opentalking.ps1", "package.json 缺少 opentalking:start。");
assert(packageJson.scripts["opentalking:check"] === "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-opentalking-assets.ps1", "package.json 缺少 opentalking:check。");

console.log("goal acceptance audit passed");
