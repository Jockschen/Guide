import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const tourist = readFileSync(path.join(root, "components", "TouristExperience.tsx"), "utf-8");
const api = readFileSync(path.join(root, "lib", "api.ts"), "utf-8");
const types = readFileSync(path.join(root, "lib", "types.ts"), "utf-8");
const e2eBenchmark = readFileSync(path.join(root, "lib", "e2eBenchmark.ts"), "utf-8");
const digitalHuman = readFileSync(path.join(root, "components", "DigitalHuman.tsx"), "utf-8");
const sessionHookPath = path.join(root, "components", "useOpenTalkingSession.ts");
const itineraryPath = path.join(root, "components", "ItineraryPanel.tsx");
const sessionHook = existsSync(sessionHookPath) ? readFileSync(sessionHookPath, "utf-8") : "";
const itinerary = existsSync(itineraryPath) ? readFileSync(itineraryPath, "utf-8") : "";
const css = readFileSync(path.join(root, "app", "globals.css"), "utf-8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

const toggleStart = tourist.indexOf("function toggleListening()");
const backendRecording = tourist.indexOf("startBackendRecording()", toggleStart);
const browserRecognition = tourist.indexOf("const Recognition", toggleStart);

assert(toggleStart >= 0, "未找到语音输入入口 toggleListening。");
assert(backendRecording >= 0, "语音输入未调用后端录音识别入口。");
assert(browserRecognition >= 0, "未找到浏览器语音兜底逻辑。");
assert(backendRecording < browserRecognition, "语音输入没有优先走后端 ASR 适配层。");
assert(tourist.includes("/api/asr/transcribe"), "游客端未接入后端 ASR 转写接口。");
assert(tourist.includes("encodePcm16") && tourist.includes("question.pcm"), "游客端录音未优先生成短语音识别需要的单声道语音。");
assert(tourist.includes("/api/tts/synthesize"), "游客端未接入后端 TTS 合成接口。");
assert(api.includes("TextDecoder") && api.includes("getReader()"), "API 层未逐行解析 NDJSON 响应。");
assert(api.includes("AbortSignal") && api.includes("signal"), "NDJSON 请求未接入取消信号。");
for (const eventName of ["meta", "delta", "narration", "done", "error"]) {
  assert(types.includes(`\"${eventName}\"`), `流式问答缺少 ${eventName} 事件契约。`);
  assert(tourist.includes(`case \"${eventName}\"`), `游客端未消费 ${eventName} 流式事件。`);
}
assert(tourist.includes('"/api/chat/stream"'), "游客端仍未调用流式问答接口。");
assert(tourist.includes("new AbortController") && tourist.includes("chatAbortRef.current?.abort()"), "新问题未取消旧问答流。");
assert(tourist.includes("openTalking.interrupt()"), "新问题未打断当前数字人讲解。");
assert(tourist.includes("enqueueNarration") && tourist.includes("drainNarrationQueue"), "首句 TTS 与后续单段预取未经过顺序播放队列。");
assert(tourist.includes('"faq-fast-path"') && tourist.includes('"qwen-stream"') && tourist.includes('"local-retrieval"'), "前端未识别 FAQ、Qwen 流式与本地资料 Provider。");
assert(!tourist.includes('apiPost<ChatResponse>("/api/chat"'), "游客问答仍等待串行完整回答。");
assert(!tourist.includes("void speak(data.answer)"), "done 事件后仍重复播报整段回答。");
assert(tourist.includes("avatarDriver") && tourist.includes("setAvatarDriver"), "游客端未保存数字人驱动元数据。");
assert(tourist.includes("lipsync.driver"), "游客端未消费后端返回的数字人驱动元数据。");
assert(!tourist.includes("const demoVideoStarted = showDemoDriverVideo()"), "游客端不应在 TTS 开始前抢先播放演示片段。");
assert(tourist.includes("voice: voicePreset"), "TTS 请求未携带音色设置。");
assert(tourist.includes("style: guideStyle"), "TTS 请求未携带讲解风格。");
assert(tourist.includes("speed: speechRate"), "TTS 请求未携带语速设置。");
assert(tourist.includes("volume: speechVolume"), "TTS 请求未携带音量设置。");
assert(tourist.includes("audio.playbackRate = speechRate"), "本地音频没有应用真实语速，语速滑块只改变了界面状态。");
assert(tourist.includes("activeAudioRef.current.volume = speechVolume"), "播放中的音频没有实时响应音量滑块。");
assert(tourist.includes("activeAudioRef.current.playbackRate = speechRate"), "播放中的音频没有实时响应语速滑块。");
assert(tourist.includes("normalizeSpeechText") && tourist.includes("formatClockTime"), "游客端未在播报前规范化时间朗读。");
assert(tourist.includes("splitNarrationSegments"), "游客端没有按自然语义拆分讲解。 ");
assert(tourist.includes("prepareDriverVideo"), "游客端没有在音频播放时并行准备讲解画面。 ");
assert(tourist.includes("blendDriverVideo"), "游客端没有无中断切入讲解画面的边界。 ");
assert(tourist.includes("let tracking = false"), "暂停后继续播放会重复启动数字人回应动画。 ");
assert(tourist.includes("Number.isFinite(driverVideo.duration)"), "恢复讲解画面时缺少有效时长保护。 ");
assert(!tourist.includes("正在生成口型视频"), "游客端仍暴露技术性生成状态。 ");
assert(!tourist.includes("同步口型讲解"), "游客端仍暴露技术性口型标签。 ");
assert(!tourist.includes("口型链路异常"), "游客端仍向游客暴露内部错误状态。 ");
assert(tourist.includes("字幕"), "游客端缺少字幕开关文案。");
assert(tourist.includes("音色") && tourist.includes("风格") && tourist.includes("语速") && tourist.includes("音量"), "游客端缺少体验配置控件。");
for (const token of ["avatar-presentation", 'aria-live="polite"', 'aria-atomic="true"', "data-expression={expression}", "expression-${expression}"]) {
  assert(digitalHuman.includes(token), `数字人舞台缺少 ${token}。`);
}
assert(digitalHuman.includes('<div className="subtitle-panel" aria-live="polite" aria-atomic="true">'), "字幕 live region 的位置或原子播报语义不正确。");
assert(digitalHuman.includes('expression === "speaking" && speaking'), "暂停后仍可能保留 is-speaking class。");
assert(!digitalHuman.includes("avatar-driver-chip") && !digitalHuman.includes("avatar-driver-layer"), "数字人仍有重复的驱动状态浮层。");
assert(!tourist.includes("visibleDriverLabel") && !tourist.includes("driverLabel={"), "游客端仍传递实现型驱动标签。");
const listeningPriority = tourist.indexOf("listening ? GUIDE_STATUS.listening");
const pausedPriority = tourist.indexOf("speechPaused ? GUIDE_STATUS.paused");
const speakingPriority = tourist.indexOf("speaking ? GUIDE_STATUS.speaking");
const loadingPriority = tourist.indexOf("loading ? GUIDE_STATUS.thinking");
assert(listeningPriority >= 0 && listeningPriority < pausedPriority && pausedPriority < speakingPriority && speakingPriority < loadingPriority, "展示状态没有保证暂停态与边生成边播报的优先级。");
assert(tourist.includes("presentationStatus === GUIDE_STATUS.speaking") && tourist.includes("statusLabel={presentationStatus}"), "视觉 expression 未由统一 presentationStatus 驱动。");
assert(!tourist.includes('className="guide-online"'), "游客顶栏仍有固定的第二个导游状态徽标。");
const playbackStart = tourist.indexOf('<div className="playback-strip">');
if (playbackStart >= 0) {
  const playbackEnd = tourist.indexOf("</div>", playbackStart);
  const playbackBlock = tourist.slice(playbackStart, playbackEnd);
  assert(playbackBlock.includes("<span>{presentationStatus}</span>"), "播放控制区没有直接复用统一 presentationStatus。");
  for (const bypassStatus of ["导游在线", "正在聆听", "正在整理", "正在讲解", "讲解已暂停"]) {
    assert(!playbackBlock.includes(bypassStatus), `播放控制区仍旁路硬编码状态：${bypassStatus}。`);
  }
}
const deltaCaseStart = tourist.indexOf('case "delta":');
const narrationCaseStart = tourist.indexOf('case "narration"', deltaCaseStart);
assert(deltaCaseStart >= 0 && narrationCaseStart > deltaCaseStart, "无法定位 chat stream 的 delta 区段。");
assert(!tourist.slice(deltaCaseStart, narrationCaseStart).includes("setSubtitle"), "逐 token delta 仍在更新讲解字幕。");
const doneCaseStart = tourist.indexOf('case "done"', narrationCaseStart);
const errorCaseStart = tourist.indexOf('case "error"', doneCaseStart);
assert(doneCaseStart > narrationCaseStart && errorCaseStart > doneCaseStart, "无法定位 chat stream 的 done 区段。");
assert(!tourist.slice(doneCaseStart, errorCaseStart).includes("setSubtitle"), "非分段 done 仍在覆盖讲解字幕。");
const narrationPlaybackStart = tourist.indexOf("async function playNarrationSegment(");
const narrationPlaybackEnd = tourist.indexOf("async function requestNarrationAudio(", narrationPlaybackStart);
assert(narrationPlaybackStart >= 0 && narrationPlaybackEnd > narrationPlaybackStart && tourist.slice(narrationPlaybackStart, narrationPlaybackEnd).includes("setSubtitle(text)"), "讲解字幕没有在 narration segment 开始播放时更新。");
for (const selector of [".expression-friendly", ".expression-listening", ".expression-thinking", ".expression-speaking"]) {
  assert(css.includes(selector), `数字人缺少状态效果 ${selector}。`);
}
for (const roiToken of ["requestVideoFrameCallback", "canvas.width = 72", "canvas.height = 54", "video.videoWidth * 0.41", "video.videoHeight * 0.42", "video.videoWidth * 0.18", "video.videoHeight * 0.15", "onFirstVisibleMouth", "srcObject"]) {
  assert(digitalHuman.includes(roiToken), `真实嘴部 ROI 采集缺少 ${roiToken}。`);
}
const reducedMotionCss = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
assert(reducedMotionCss.includes(".expression-listening .avatar-status") && reducedMotionCss.includes(".expression-thinking .avatar-media-frame") && reducedMotionCss.includes("animation: none"), "状态动画没有显式支持减少动态效果。");
const mobileCss = css.slice(css.indexOf("@media (max-width: 600px)"));
assert(!/\.subtitle-panel\s*\{[^}]*display:\s*none/s.test(mobileCss), "手机端仍隐藏字幕。");
const mobileStarButtonRule = mobileCss.match(/\.star-buttons button\s*\{([^}]*)\}/s)?.[1] || "";
const mobileFeedbackFieldRule = mobileCss.match(/\.star-feedback input,\s*\.star-feedback form button\s*\{([^}]*)\}/s)?.[1] || "";
assert(
  /min-width:\s*44px/.test(mobileStarButtonRule)
    && /min-height:\s*44px/.test(mobileStarButtonRule)
    && /min-height:\s*44px/.test(mobileFeedbackFieldRule),
  "手机端星级评分、建议输入和提交按钮未达到 44 像素触控尺寸。"
);
assert(tourist.includes("subtitlesEnabled ? subtitle : null") && digitalHuman.includes("subtitle !== null"), "关闭字幕后仍会渲染 live 字幕内容。");
assert(!digitalHuman.includes("syntheticMotionEnabled && !driverPending"), "讲解画面准备时不应停掉数字人的自然回应。");
assert(!digitalHuman.includes("avatar-lip-sync") && !digitalHuman.includes("avatar-eye-shade"), "数字人不应在人像上叠加伪口型或眉毛贴片。");
assert(css.includes("--radius-card"), "游客端缺少收紧后的卡片圆角令牌。 ");
assert(css.includes(".tourist-shell .avatar-video-driver.is-ready"), "真实讲解画面缺少柔和切入样式。 ");
assert(css.includes("focus-visible"), "游客端缺少键盘焦点反馈。 ");
assert(css.includes("prefers-reduced-motion"), "游客端缺少减少动态效果的支持。 ");

assert(tourist.includes("useOpenTalkingSession"), "游客端未接入 OpenTalking 会话 Hook。");
assert(sessionHook.includes("new RTCPeerConnection") && sessionHook.includes('addTransceiver("video"') && sessionHook.includes('addTransceiver("audio"'), "OpenTalking Hook 未建立仅接收音视频的 WebRTC 连接。");
assert(sessionHook.includes("/api/avatar/sessions") && sessionHook.includes("/webrtc/offer") && sessionHook.includes("/audio") && sessionHook.includes("/interrupt"), "OpenTalking Hook 未消费同源会话、协商、音频和打断端点。");
assert(sessionHook.includes("new EventSource") && sessionHook.includes('/events'), "OpenTalking Hook 未订阅同源会话事件流。");
assert(sessionHook.includes("waitForSessionReady") && sessionHook.includes("/api/avatar/sessions/${encodeURIComponent(sessionId)}"), "OpenTalking Hook 未等待 initializing 会话进入 ready 就提前协商 WebRTC。");
assert(sessionHook.includes('"worker_ready"') && sessionHook.includes('"speaking"'), "OpenTalking Hook 未按官方 worker_ready/ready/speaking 状态等待可协商会话。");
assert(!sessionHook.includes('["ready", "created"]'), "OpenTalking Hook 把仅写入 Redis 的 created 状态误判为可协商，数字人会因此没有视频轨。");
assert((sessionHook.includes("peer.close()") || sessionHook.includes("peer?.close()")) && sessionHook.includes("track.stop()") && sessionHook.includes("DELETE"), "OpenTalking Hook 缺少 Peer、媒体轨和服务端会话清理。");
assert(digitalHuman.includes("stream") && digitalHuman.includes("srcObject"), "数字人舞台未渲染 WebRTC 媒体流。");
assert(digitalHuman.includes("avatar-portrait is-hidden"), "实时视频出现后仍保留静态人像，页面会叠出两个数字人。");
assert(digitalHuman.includes("muted") && digitalHuman.includes("avatar-stream"), "WebRTC 数字人视频未静音自动播放，浏览器可能拦截视频轨。");
assert(!tourist.includes("playSilentClock") && !tourist.includes("audio.muted = true"), "WebRTC 画面启用时错误静音了 Vivo TTS，游客会看到口型但听不到讲解。");

for (const mark of ["recording_stop", "asr_start", "asr_done", "chat_start", "first_narration", "tts_start", "tts_done", "audio_upload_start", "audio_upload_ack", "first_valid_audio", "first_visible_mouth"]) {
  assert(e2eBenchmark.includes(`"${mark}"`), `E2E benchmark 缺少 ${mark} 时间点。`);
}
assert(e2eBenchmark.includes("performance.now()"), "E2E benchmark 未使用同一浏览器单调时钟。");
assert(e2eBenchmark.includes("end_to_end_ms") && e2eBenchmark.includes("Math.max(validAudio, visibleMouth)") && e2eBenchmark.includes("recording_stop"), "E2E benchmark 未以录音结束到有效音频与可见口型均就绪作为权威总时延。");
assert(e2eBenchmark.includes("window.__LINGJING_E2E_BENCHMARK__") && e2eBenchmark.includes("download") && e2eBenchmark.includes("getSamples") && e2eBenchmark.includes("clear"), "E2E benchmark 缺少隐藏导出 API。");
assert(e2eBenchmark.includes("localStorage") && e2eBenchmark.includes('benchmark") === "1"'), "E2E benchmark 未限制为 ?benchmark=1 或未持久化样本。");
assert(tourist.includes("createVoiceBenchmarkTrace") && tourist.includes("tryCompleteBenchmarkTrace") && tourist.includes("failBenchmarkTrace"), "游客真实语音链路未接入 benchmark trace 生命周期。");
assert(tourist.includes('addEventListener("playing"') && tourist.includes("firstAudiblePcmOffsetMs"), "E2E benchmark 未以真实音频 playing 和首个非静音 PCM 偏移估算有效音节。");
assert(sessionHook.includes("onUploadStart") && sessionHook.includes("onUploadAck") && sessionHook.includes("performance.now()"), "OpenTalking Hook 未记录真实音频上传时间。");
assert(digitalHuman.includes("requestVideoFrameCallback") && digitalHuman.includes("getImageData") && digitalHuman.includes("onFirstVisibleMouth"), "数字人舞台未用真实 WebRTC 帧和嘴部 ROI 检测首个可见口型。");

assert(tourist.includes('type GuideMode = "conversation" | "itinerary"'), "导览区缺少对话/当前游线双模式状态。");
assert(tourist.includes('role="tablist"') && tourist.includes('role="tab"') && tourist.includes('role="tabpanel"'), "导览区标签页缺少可访问语义。");
assert(tourist.includes('role="log"') && tourist.includes('aria-live="polite"'), "对话区缺少日志与播报语义。");
assert(tourist.includes("ItinerarySummary") && tourist.includes("ItineraryPanel"), "路线未同时提供回答内摘要和导览区完整视图。");
assert(!tourist.includes("if (!routeRequested) setVisibleRoutePlan(null)"), "普通问答仍会清空当前路线。");
assert(tourist.includes("closeCurrentRoute") && tourist.includes("setVisibleRoutePlan(null)"), "路线缺少显式关闭行为。");
assert(itinerary.includes("讲这一站") && itinerary.includes("onNarrateStop"), "当前游线缺少不清路线的站点讲解入口。");
assert(itinerary.includes('fill="none"') && itinerary.includes("route-track-line"), "游线路径未关闭 SVG 默认填充，会出现黑色三角形。");
assert(css.includes(".route-track-line") && css.includes(".route-track-keyline"), "游线路径缺少与底图匹配的双层线样式。");
assert(css.includes("aspect-ratio: 16 / 9") && css.includes("background-size: 100% 100%"), "路线底图仍会被裁切，百分比坐标无法与景点位置对齐。");
assert(!tourist.includes("route-side-panel"), "路线仍被追加为第三个网格面板，而不是复用同一导览区。");

assert(!tourist.includes("handleAvatarMedia") && !tourist.includes("avatar-media-controls"), "游客端仍允许替换数字人形象。");
assert(tourist.includes("handleQuestionImage") && tourist.includes("captureCameraFrame"), "游客端未保留照片/相机多模态提问。");
assert(tourist.includes("/api/feedback/text"), "游客端文字反馈未接入新的体验闭环接口。");
assert(tourist.includes("sentimentFromRating(rating)"), "游客反馈仍向后端传递中文情感值，会被 positive/neutral/negative 契约拒绝。");
assert(tourist.includes('仅提交星级评价'), "纯星级反馈没有可入库的文字说明，会被最小长度校验拒绝。");
assert(css.includes("--paper-warm") && css.includes("--ink-blue") && css.includes("--cinnabar"), "山水长卷暖白、墨蓝和朱砂设计令牌不完整。");
assert(css.includes('url("/assets/generated/hero-lingshan-v2.png")'), "主页仍在使用与灵山数字人不协调的旧景区背景图。");
assert(tourist.includes("/assets/generated/app-icon-v2.png"), "游客端仍在使用与新视觉系统不一致的旧品牌图标。");
assert(itinerary.includes("/assets/generated/route-map-lingshan-v2.png"), "个性化推荐游线仍在使用通用虚构路线底图。");
assert(tourist.includes("SuggestionIcon") && tourist.includes("<Route"), "推荐提问仍重复使用同一个图标，缺少语义区分。");
assert(css.includes("@media (max-width: 600px)") && css.includes(".guide-panel"), "缺少 390 像素全宽导览区布局。");

const followUpIndex = tourist.indexOf("<FollowUpSuggestions");
const feedbackIndex = tourist.indexOf("<StarFeedback");
assert(followUpIndex >= 0 && feedbackIndex > followUpIndex, "追问标签必须先于回答尾部反馈区。");
assert(tourist.includes("feedback-note-toggle") && tourist.includes("showNote"), "文字建议未在评分后按需展开。");
assert(tourist.includes("正在查找景区资料…"), "加载状态未使用统一游客语言。");
assert(itinerary.includes('aria-label="游线示意图"'), "静态路线图片仍被称为真实地图。");
assert(css.includes("max-width: 64ch") && css.includes(".markdown-body blockquote"), "回答正文或资料依据缺少阅读层级。");

console.log("tourist interaction flow audit passed");
