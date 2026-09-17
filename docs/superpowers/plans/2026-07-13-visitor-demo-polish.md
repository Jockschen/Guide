# 游客端演示体验优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将游客端落实为已确认的 A「舞台留白」方案，统一数字人状态、字幕与对话层级，压缩后台自测说明，并用真实音视频证据验证质量与速度不回退。

**Architecture:** 保持 `TouristExperience` 负责问答、语音和状态编排，`DigitalHuman` 只负责状态、媒体与字幕舞台；视觉变化仅作用于 DOM/CSS 展示层，不改变 WebRTC 媒体流、720×720 原始帧或嘴部 ROI。现有 Node 静态审计先写成失败契约，再修改组件；后台仍由 `CompetitionPanels` 展示自测边界，最终复用现有离线、实时 WebRTC 与浏览器端到端验收链路。

**Tech Stack:** Next.js 15、React 19、TypeScript 5.6、原生 CSS、Node.js 静态审计、Python unittest、OpenTalking session + WebRTC。

## Global Constraints

- 视觉方向固定为 A「舞台留白」；不新增游客页面或新的导航层级。
- 不改 FAQ 快速通道、Qwen 首句流式、分段 TTS、OpenTalking session 复用和浏览器端延迟采集。
- OpenTalking 视频继续使用完整原始媒体坐标；仅改变外层容器尺寸、位置、留白和裁切。
- 游客状态只允许：`导游在线`、`正在聆听`、`正在整理`、`正在讲解`、`讲解已暂停`。
- 字幕位于媒体框下方、最多两行，桌面和手机均可见，使用 `aria-live="polite"`。
- 游客界面不得出现 QuickTalk、WebRTC、provider、session、模型 ID、服务地址或内部错误名。
- `friendly / listening / thinking / speaking` 仅表达交互状态；`GuideStatus` 是状态文案与视觉效果的唯一来源，不得叠加 CSS 假嘴型或宣称真实情绪驱动。
- 不通过缩短回答、预录音频、mock 结果或降低生成分辨率制造速度提升。
- 本地题集、自检和像素运动证据不得写成官方成绩或专家自然度结论。
- 不改定位辅助、坐标或路线起点能力。
- 每个任务以可重复的测试结果作为检查点，不添加版本提交步骤。

---

## File Structure

### Modify

- `components/DigitalHuman.tsx`：唯一状态胶囊、真实媒体层、舞台下字幕和状态 class。
- `components/TouristExperience.tsx`：五态文案、数字人 props、回答/追问/反馈顺序和游客加载文案。
- `components/ItineraryPanel.tsx`：把静态路线图片明确称为“游线示意图”。
- `components/admin/CompetitionPanels.tsx`：将自测方法说明压缩为题集、判定、结果用途三步。
- `app/globals.css`：A 方案布局、移动字幕、状态效果、正文/反馈层级和紧凑自测方法。
- `scripts/audit-tourist-copy.mjs`：覆盖全部游客可见组件并阻止旧状态及技术词回流。
- `scripts/audit-tourist-flow.mjs`：锁定舞台 DOM、字幕、状态效果和对话层级。
- `scripts/audit-admin-competition.mjs`：锁定紧凑三步自测说明与本地/官方边界。
- `scripts/audit-goal-acceptance.mjs`：同步新的游客端、后台和演示验收契约。
- `scripts/self-check.mjs`：运行时 bundle 改为检查五态文案。
- `docs/demo-runbook.md`：增加桌面、手机、字幕、状态与真实口型检查清单。

### Preserve Without Structural Changes

- `components/useOpenTalkingSession.ts`：session 建立、音视频轨、音频上传、中断和清理。
- `lib/e2eBenchmark.ts`：真实音频与首个可见口型时间点。
- `components/DigitalHuman.tsx:81-138`：`requestVideoFrameCallback` 嘴部 ROI 采样。
- `scripts/validate_opentalking_webrtc.py`：六项真实 WebRTC 检查。

---

### Task 1: A「舞台留白」、唯一状态与克制表情

**Files:**
- Modify: `scripts/audit-tourist-copy.mjs:5-34`
- Modify: `scripts/audit-tourist-flow.mjs:47-77`
- Modify: `scripts/audit-goal-acceptance.mjs:230-329`
- Modify: `scripts/self-check.mjs:243-244`
- Modify: `components/DigitalHuman.tsx:3-46,148-200`
- Modify: `components/TouristExperience.tsx:22,152-185,331-350,357-1208,1376-1395`
- Modify: `app/globals.css:204-361,2481-2555,2648-2731`

**Interfaces:**
- Consumes: `statusLabel`, `expression`,静态形象、兼容视频、WebRTC `MediaStream`、`driverVideoRef` 和嘴部检测回调。
- Produces: `GuideStatus` 五态类型、`.avatar-presentation` 三行舞台、`.expression-*` 状态样式；关闭字幕时不渲染 live region，媒体和 benchmark 回调签名保持不变。

- [ ] **Step 1: 先写会失败的舞台与文案审计**

在 `audit-tourist-copy.mjs` 扩大游客文件并加入旧状态/技术词：

```js
const files = [
  path.join(root, "components", "TouristExperience.tsx"),
  path.join(root, "components", "DigitalHuman.tsx"),
  path.join(root, "components", "ItineraryPanel.tsx")
];

const forbiddenTerms = [
  "ASR", "TTS", "Qwen", "Vivo", "Provider", "provider", "mock",
  "OpenTalking", "QuickTalk", "WebRTC", "session", "模型 ID", "API Key",
  "生成口型中", "同步口型讲解", "口型链路异常", "口型视频生成失败",
  "讲解准备中", "正在为你讲解", "正在整理资料", "正在查找本地资料",
  "正在整理景区问答", "正在为你准备讲解", "正在播报", "正在识别"
];
```

在 `audit-tourist-flow.mjs` 增加新契约，并删除要求 `driverLabel`、`avatar-driver-chip`、`avatar-driver-layer` 的旧断言：

```js
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
assert(tourist.includes("subtitlesEnabled ? subtitle : null") && digitalHuman.includes("subtitle !== null"), "关闭字幕后仍会渲染 live 字幕内容。");
```

同步 `audit-goal-acceptance.mjs` 的数字人/CSS必备项，并把 `self-check.mjs` 的运行时必备状态替换为：

```js
["导游在线", "正在聆听", "正在整理", "正在讲解", "讲解已暂停"]
```

- [ ] **Step 2: 运行审计并确认旧实现被拒绝**

Run:

```powershell
npm run copy-audit
npm run flow-audit
npm run goal-audit
```

Expected: 三个命令至少各有一个非零退出；输出分别指出旧状态文案、缺少 `avatar-presentation` 或缺少 `.expression-*` 状态样式。

- [ ] **Step 3: 将 `DigitalHuman` 改为唯一状态和三行舞台**

删除 lucide 图标导入、`driverLabel` prop 与两个重复浮层，新增五态类型，并用以下 JSX 替换当前 return：

```tsx
export type GuideStatus = "导游在线" | "正在聆听" | "正在整理" | "正在讲解" | "讲解已暂停";

return (
  <section
    className={`avatar-stage expression-${expression} ${expression === "speaking" && speaking ? "is-speaking" : ""}`}
    data-expression={expression}
    aria-label="数字人导游"
  >
    <div className="scenic-signature" aria-label="灵山胜境，无锡">
      <span>灵山胜境</span>
      <b>无锡</b>
    </div>
    <div className="avatar-presentation">
      <div className="avatar-status" role="status">
        <span className={statusReady ? "status-dot ready" : "status-dot"} />
        <span>{statusLabel}</span>
      </div>
      <div className="avatar-media-frame" aria-busy={driverPending}>
        <img className={streamVisible || driverVideoReady ? "avatar-portrait is-hidden" : "avatar-portrait"} src={imageUrl || "/assets/generated/avatar-guide-v2.png"} alt="灵境导游数字人形象" />
        {driverVideoUrl ? (
          <video
            ref={driverVideoRef}
            className={driverVideoReady ? "avatar-video avatar-video-driver is-ready" : "avatar-video avatar-video-driver"}
            src={driverVideoUrl}
            poster={imageUrl || "/assets/generated/avatar-guide-v2.png"}
            aria-label="数字人讲解画面"
            autoPlay
            playsInline
            preload="auto"
            onCanPlay={() => setDriverVideoReady(true)}
            onLoadedData={() => setDriverVideoReady(true)}
            onPlaying={() => setDriverVideoReady(true)}
          />
        ) : null}
        <video
          ref={streamVideoRef}
          className={streamVisible ? "avatar-video avatar-stream is-ready" : "avatar-video avatar-stream"}
          aria-label="数字人实时讲解画面"
          autoPlay
          muted
          playsInline
          onCanPlay={() => setStreamVisible(true)}
          onPlaying={() => setStreamVisible(true)}
        />
      </div>
      {subtitle !== null ? (
        <div className="subtitle-panel" aria-live="polite" aria-atomic="true">
          <p>{subtitle || "欢迎来到灵山胜境，我可以陪你问景点、听讲解、规划路线。"}</p>
        </div>
      ) : null}
    </div>
  </section>
);
```

`statusLabel` 的 prop 类型改为 `GuideStatus`，`subtitle` 改为 `string | null`；`null` 表示游客主动关闭字幕。保留 `driverPending` 仅用于媒体框的 `aria-busy`，不要改 `useEffect`、视频 ref、`srcObject`、72×54 采样画布或源 ROI 的 `0.41 / 0.42 / 0.18 / 0.15`。字幕继续按 narration segment 更新，不绑定逐 token 回答流。

- [ ] **Step 4: 在 `TouristExperience` 集中五态并移除驱动标签**

```tsx
import { DigitalHuman, type GuideStatus, type VisemeFrame } from "./DigitalHuman";

const GUIDE_STATUS = {
  online: "导游在线",
  listening: "正在聆听",
  thinking: "正在整理",
  speaking: "正在讲解",
  paused: "讲解已暂停"
} as const satisfies Record<string, GuideStatus>;

const [statusLabel, setStatusLabel] = useState<GuideStatus>(GUIDE_STATUS.online);

const presentationStatus: GuideStatus = listening
  ? GUIDE_STATUS.listening
  : speechPaused
    ? GUIDE_STATUS.paused
    : speaking
      ? GUIDE_STATUS.speaking
      : loading
        ? GUIDE_STATUS.thinking
        : statusLabel;

const avatarExpression = presentationStatus === GUIDE_STATUS.listening
  ? "listening"
  : presentationStatus === GUIDE_STATUS.thinking
    ? "thinking"
    : presentationStatus === GUIDE_STATUS.speaking
      ? "speaking"
      : "friendly";
```

所有 `setStatusLabel` 只使用上述常量：提交/检索/识别用 `thinking`，录音用 `listening`，音频开始和恢复用 `speaking`，暂停用 `paused`，停止、结束与错误降级用 `online`。把 `presentationStatus` 传入 `<DigitalHuman statusLabel={presentationStatus} />`；它保证暂停优先于说话、说话优先于仍在进行的文本生成。传给数字人的字幕改为 `subtitle={subtitlesEnabled ? subtitle : null}`。删除 `visibleDriverLabel` 及 `<DigitalHuman driverLabel={...} />`，保留 `avatarDriver` 元数据和现有音频优先流程。

- [ ] **Step 5: 用 CSS 落实桌面舞台、浅色字幕与状态效果**

替换现有舞台、媒体框、状态和字幕定位规则：

```css
.avatar-stage {
  position: absolute;
  top: 112px;
  bottom: 0;
  left: 0;
  width: min(54vw, 820px);
  overflow: hidden;
}

.avatar-presentation {
  position: absolute;
  inset: 24px auto 28px clamp(46px, 6vw, 92px);
  width: min(42vw, 640px);
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 12px;
}

.avatar-media-frame {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 360px;
  overflow: hidden;
  background: #dce8ef;
  border-radius: 24px;
  box-shadow: 0 18px 42px rgba(16, 38, 56, 0.18);
}

.avatar-status {
  position: static;
  z-index: 5;
  justify-self: center;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 8px 12px;
  color: var(--ink-blue);
  background: rgba(251, 248, 241, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  font-size: 14px;
}

.subtitle-panel {
  position: static;
  z-index: 5;
  padding: 12px 16px;
  color: var(--ink-blue);
  background: rgba(251, 248, 241, 0.95);
  border: 1px solid rgba(18, 60, 104, 0.12);
  border-radius: 14px;
}

.subtitle-panel p {
  margin: 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  font-size: 14px;
  line-height: 1.65;
}

.expression-friendly .status-dot { background: var(--jade); }
.expression-friendly .avatar-status,
.expression-speaking .avatar-media-frame { animation: none; }
.expression-listening .status-dot { background: var(--scenic-blue); }
.expression-listening .avatar-status { animation: avatar-listening-glow 2.4s ease-in-out infinite; }
.expression-thinking .status-dot { background: #b98436; }
.expression-thinking .avatar-media-frame { animation: avatar-thinking-glow 3.2s ease-in-out infinite; }
.expression-speaking .status-dot { background: var(--jade); }
.expression-speaking .avatar-status { border-color: rgba(55, 128, 95, 0.34); }

@keyframes avatar-listening-glow {
  0%, 100% { border-color: rgba(29, 101, 173, 0.2); }
  50% { border-color: rgba(29, 101, 173, 0.58); }
}

@keyframes avatar-thinking-glow {
  0%, 100% { box-shadow: 0 18px 42px rgba(16, 38, 56, 0.16); }
  50% { box-shadow: 0 18px 48px rgba(185, 132, 54, 0.25); }
}
```

在 `max-width: 900px` 将 `.avatar-presentation` 设为 `inset: 20px 14px; width: auto;`。在 `max-width: 600px` 用以下规则替换旧的 284px 舞台、下沉媒体框和隐藏字幕：

```css
.avatar-stage { width: 100%; height: 438px; min-height: 438px; }
.avatar-presentation { inset: 10px 14px 12px; width: auto; gap: 8px; }
.avatar-media-frame { width: 100%; height: 100%; min-height: 280px; transform: none; border-radius: 24px; }
.avatar-status { justify-self: center; }
.subtitle-panel { display: block; padding: 10px 12px; border-radius: 12px; }
.subtitle-panel p { font-size: 14px; line-height: 1.55; }
.avatar-portrait, .avatar-video { object-position: center 14%; }

@media (prefers-reduced-motion: reduce) {
  .expression-listening .avatar-status,
  .expression-thinking .avatar-media-frame {
    animation: none !important;
  }
}
```

- [ ] **Step 6: 运行舞台任务的独立验收**

Run:

```powershell
npm run copy-audit
npm run flow-audit
npm run goal-audit
npm run typecheck
npm run build
```

Expected: 全部退出码为 0；审计分别打印 `tourist copy audit passed`、`tourist interaction flow audit passed`、`goal acceptance audit passed`，生产构建完成且没有 TypeScript 错误。

---

### Task 2: 字幕/文案、回答、追问与反馈层级

**Files:**
- Modify: `scripts/audit-tourist-copy.mjs:10-34`
- Modify: `scripts/audit-tourist-flow.mjs:104-128`
- Modify: `components/TouristExperience.tsx:3,1436-1521,1556-1613`
- Modify: `components/ItineraryPanel.tsx:61`
- Modify: `app/globals.css:524-760,864-891`

**Interfaces:**
- Consumes: 现有 `Message`、`latestAssistantIndex`、`followUpSuggestions` 和反馈 API 回调。
- Produces: 回答正文 → 追问标签 → 折叠反馈的固定顺序；输入框和反馈 API 契约不变。

- [ ] **Step 1: 先锁定对话层级与游客文案**

在 `audit-tourist-flow.mjs` 增加：

```js
const followUpIndex = tourist.indexOf("<FollowUpSuggestions");
const feedbackIndex = tourist.indexOf("<StarFeedback");
assert(followUpIndex >= 0 && feedbackIndex > followUpIndex, "追问标签必须先于回答尾部反馈区。");
assert(tourist.includes("feedback-note-toggle") && tourist.includes("showNote"), "文字建议未在评分后按需展开。");
assert(tourist.includes("正在查找景区资料…"), "加载状态未使用统一游客语言。");
assert(itinerary.includes('aria-label="游线示意图"'), "静态路线图片仍被称为真实地图。");
assert(css.includes("max-width: 64ch") && css.includes(".markdown-body blockquote"), "回答正文或资料依据缺少阅读层级。");
```

把 `正在为你整理景点信息` 加入 copy audit 的禁用文案。

- [ ] **Step 2: 运行审计并确认当前顺序失败**

Run:

```powershell
npm run copy-audit
npm run flow-audit
```

Expected: 非零退出；输出指出旧加载文案、追问/反馈顺序或缺少折叠反馈。

- [ ] **Step 3: 调整消息尾部顺序与可见文案**

在 assistant message 内把 `FollowUpSuggestions` 放在 `StarFeedback` 之前；加载文案改为 `正在查找景区资料…`；主输入框的输入提示改为 `问景点、演出或游线…`；`ItineraryPanel` 的图片 aria-label 改为 `游线示意图`。

给 React import 加 `useId`，并用以下实现替换 `StarFeedback`：

```tsx
function StarFeedback({ rating, onChoose, onSubmit }: {
  rating: number;
  onChoose: (rating: number) => void;
  onSubmit: (rating: number, note: string) => void;
}) {
  const [draftRating, setDraftRating] = useState(rating);
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const noteId = useId();
  const selectedRating = rating || draftRating;
  return (
    <div className="feedback-row star-feedback" aria-label="为本次回答评分">
      <div className="feedback-score-line">
        <span>这次回答有帮助吗？</span>
        <div className="star-buttons" role="radiogroup" aria-label="选择星级评分">
          {[1, 2, 3, 4, 5].map((value) => (
            <button aria-checked={selectedRating === value} aria-label={`${value} 星`} className={value <= selectedRating ? "active" : ""} key={value} onClick={() => { setDraftRating(value); onChoose(value); }} role="radio" type="button">
              <Star size={17} fill="currentColor" />
            </button>
          ))}
        </div>
      </div>
      {selectedRating ? <button className="feedback-note-toggle" type="button" onClick={() => setShowNote((value) => !value)}>{showNote ? "收起建议" : "补充建议"}</button> : null}
      {showNote && selectedRating ? (
        <form onSubmit={(event) => { event.preventDefault(); if (note.trim()) { onSubmit(selectedRating, note); setNote(""); setShowNote(false); } }}>
          <label htmlFor={noteId}>补充建议</label>
          <input id={noteId} aria-label="写下你的建议（选填）" placeholder="写下你的建议（选填）" value={note} onChange={(event) => setNote(event.target.value)} />
          <button type="submit" disabled={!note.trim()}>提交</button>
        </form>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: 收紧正文、依据、追问和反馈 CSS**

```css
.markdown-body { max-width: 64ch; font-size: 14px; line-height: 1.75; }
.markdown-body p { margin: 0 0 0.8em; }
.markdown-body blockquote { margin: 12px 0 0; padding: 8px 12px; color: var(--ink-muted); background: #f4f1e9; border: 1px solid rgba(18, 60, 104, 0.12); border-radius: 8px; font-size: 12px; }
.follow-up-suggestions { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; margin-top: 12px; }
.follow-up-suggestions > span { margin: 0; white-space: nowrap; }
.follow-up-suggestions > div { display: flex; flex: 1 1 260px; flex-wrap: wrap; gap: 6px; }
.star-feedback { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--line); }
.feedback-note-toggle { min-height: 36px; margin-top: 8px; padding: 4px 8px; color: var(--scenic-blue); background: transparent; font-size: 12px; }

@media (max-width: 600px) {
  .markdown-body blockquote,
  .follow-up-suggestions,
  .star-feedback,
  .feedback-note-toggle { font-size: 14px; }
  .follow-up-suggestions button,
  .feedback-note-toggle { min-height: 44px; }
}
```

保留 `.chat-window` 的 `flex: 1; overflow-y: auto` 和 `.ask-form` 的 `flex: 0 0 auto`，不要把输入框移入滚动消息列表。

- [ ] **Step 5: 运行对话任务的独立验收**

Run:

```powershell
npm run copy-audit
npm run flow-audit
npm run typecheck
npm run build
```

Expected: 全部退出码为 0；加载文案、示意图口径、追问/反馈顺序和折叠建议均通过审计。

---

### Task 3: 后台“本次自测如何计算”紧凑说明

**Files:**
- Modify: `scripts/audit-admin-competition.mjs:57-60`
- Modify: `scripts/audit-goal-acceptance.mjs:351-364,377-392`
- Modify: `components/admin/CompetitionPanels.tsx:397-408`
- Modify: `app/globals.css:2103-2140,2811-2814`

**Interfaces:**
- Consumes: `latest.sample_count`、`latest.passed_count`、`latest.official_evaluation`。
- Produces: `.quality-method-steps` 三步说明；准确率公式和官方边界继续由现有质量数据驱动。

- [ ] **Step 1: 先写紧凑方法区审计**

```js
assert(panels.includes('className="quality-method-steps"'), "自测方法未使用紧凑三步结构。");
for (const label of ["题集", "判定", "结果用途"]) {
  assert(panels.includes(`<b>${label}</b>`), `自测方法缺少 ${label}。`);
}
assert(!panels.includes('<details className="quality-method"'), "自测方法仍是展开式大卡。");
assert(css.includes(".quality-method-steps"), "紧凑自测步骤缺少样式。");
```

同样的必备词加入 `audit-goal-acceptance.mjs`。

- [ ] **Step 2: 运行后台审计并确认失败**

Run:

```powershell
npm run admin-audit
npm run goal-audit
```

Expected: 非零退出；输出指出缺少 `.quality-method-steps` 或仍使用 `<details>`。

- [ ] **Step 3: 替换自测方法 JSX**

用以下 section 替换当前 `details.quality-method`，其余结论卡、失败题和历史记录保持数据驱动：

```tsx
<section className="quality-method" aria-labelledby="quality-method-title">
  <header className="quality-method-head">
    <h3 id="quality-method-title">本次自测如何计算</h3>
    <p>三步说明本地结果的来源、判定和用途。</p>
  </header>
  <ol className="quality-method-steps">
    <li><span>01</span><div><b>题集</b><p>使用本地固定的 {latest.sample_count} 道景区事实题。</p></div></li>
    <li><span>02</span><div><b>判定</b><p>关键事实与资料来源都通过，才计为答对。</p></div></li>
    <li><span>03</span><div><b>结果用途</b><p>用于本机回归和改进；比赛成绩以官方评审为准。</p></div></li>
  </ol>
</section>
```

- [ ] **Step 4: 替换方法区 CSS 并保持移动端单列**

```css
.quality-method { margin-top: 18px; padding: 16px 18px 18px; background: #faf8f3; border: 1px solid var(--line); border-radius: 12px; }
.quality-method-head { display: flex; align-items: baseline; justify-content: space-between; gap: 18px; }
.quality-method-head h3 { margin: 0; color: var(--ink-blue); font: 700 17px/1.3 var(--font-serif); }
.quality-method-head p { max-width: 34ch; margin: 0; color: var(--ink-muted); font-size: 12px; }
.quality-method-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 14px 0 0; padding: 0; list-style: none; }
.quality-method-steps li { min-height: 88px; display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 8px; align-content: start; padding: 10px 12px; background: #f2eee6; border-radius: 9px; }
.quality-method-steps li > span { color: var(--cinnabar); font-size: 11px; font-weight: 700; }
.quality-method-steps b { color: var(--ink-blue); }
.quality-method-steps p { max-width: 30ch; margin: 5px 0 0; color: var(--ink-muted); font-size: 12px; line-height: 1.55; }
```

在 `max-width: 600px` 使用 `.quality-method-head { display: block; }` 和 `.quality-method-steps { grid-template-columns: 1fr; }`，并把 `.quality-method-head p`、步骤编号与步骤说明统一到至少 14px；删除旧 `.quality-method > div` 移动规则。

- [ ] **Step 5: 运行后台任务的独立验收**

Run:

```powershell
npm run admin-audit
npm run goal-audit
npm run typecheck
npm run build
```

Expected: 全部退出码为 0；审计确认“题集/判定/结果用途”、`正确题数 ÷ 总题数` 和“本地自测”边界同时存在。

---

### Task 4: 真实质量、速度与视觉验收

**Files:**
- Modify: `scripts/audit-goal-acceptance.mjs:463-480`
- Modify: `docs/demo-runbook.md:19-31`
- Verify: `reports/self-check-latest.json`
- Verify: `reports/live-service-check-latest.json`
- Verify: `reports/quality/opentalking-webrtc-latest.json`
- Verify: `reports/quality/e2e-latency-latest.json`

**Interfaces:**
- Consumes: 已完成的 UI、真实 ASR/TTS、OpenTalking session、WebRTC 轨和浏览器 benchmark 样本。
- Produces: 离线回归报告、实时链路报告、六项口型运动报告和严格端到端报告；报告边界不变。

- [ ] **Step 1: 先让目标审计要求新的演示检查清单**

在 `audit-goal-acceptance.mjs` 对 `demoRunbook` 增加：

```js
assertIncludes(demoRunbook, [
  "字幕位于数字人媒体框下方",
  "手机端字幕仍然可见",
  "导游在线 → 正在聆听 → 正在整理 → 正在讲解",
  "状态反馈不代替真实口型",
  "减少动态效果"
], "docs/demo-runbook.md");
```

Run: `npm run goal-audit`

Expected: 非零退出并指出 runbook 缺少上述检查项。

- [ ] **Step 2: 在 runbook 写入精确现场检查**

```markdown
## 界面与状态检查

- 桌面端：数字人媒体框约占左侧舞台 40% 至 44%，保留脸部和上半身；字幕位于数字人媒体框下方，不遮挡口型、胸口或右侧对话。
- 手机端：字幕仍然可见，最多两行；对话输入框位于面板底部且可直接操作。
- 状态顺序：导游在线 → 正在聆听 → 正在整理 → 正在讲解；暂停后显示“讲解已暂停”。
- 状态反馈不代替真实口型；说话时必须由真实音频驱动的 WebRTC 视频证明嘴部运动。
- 系统开启“减少动态效果”后，状态文字和颜色仍然可见，聆听与整理的无限动画停止。
- 后台方法说明只展示题集、判定和结果用途，并明确本地自测不等于官方成绩。
```

Run: `npm run goal-audit`

Expected: 退出码 0，打印 `goal acceptance audit passed`。

- [ ] **Step 3: 运行完整离线回归**

```powershell
npm run startup-audit
npm run copy-audit
npm run flow-audit
npm run admin-audit
npm run goal-audit
npm run typecheck
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_*.py
npm run build
npm run self-check
```

Expected: 所有命令退出码为 0；`reports/self-check-latest.json` 为 `ok: true`、`mode: "offline-regression"`、`competition_evidence: false`。该报告只证明回归通过。

- [ ] **Step 4: 启动真实服务并检查实时能力**

在独立 PowerShell 窗口运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -KeepAlive
```

服务就绪后运行：

```powershell
$runtime = Get-Content -LiteralPath 'backend\storage\runtime-ports.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$backend = $runtime.api_base
$env:LIVE_CHECK_STRICT = "1"
$env:LIVE_CHECK_BASE_URL = $backend
npm run live-check

.\third_party\opentalking\.venv\Scripts\python.exe scripts\validate_opentalking_webrtc.py `
  --base-url $backend `
  --target-fps 25 `
  --target-resolution 720x720
```

Expected: `live-check` 退出码 0 且报告为 `strict: true`。`reports/quality/opentalking-webrtc-latest.json` 的 `track_kinds` 同时包含 `audio` 和 `video`，六项 `checks` 均为 `true`，音频 provider 不是 mock；同时 `stream.width === 720`、`stream.height === 720`、`stream.resolution === "720x720"`、`profile.target_fps === 25`、`stream.media_timeline_fps === 25`。只记录 `validator_decode_fps` 的实际值，不要求它等于 25。

- [ ] **Step 5: 做桌面与手机视觉检查**

桌面使用 1440×900，手机使用 390×844。每个尺寸依次检查：只有一个数字人；脸和上半身可见；媒体框不贴底；状态胶囊位于人物上方；字幕在媒体框下方且最多两行；手机字幕没有消失；回答、追问、反馈和输入框不互相覆盖。切换聆听、整理、讲解和暂停，确认只有胶囊/柔光变化，没有假嘴型或循环晃动。再开启系统“减少动态效果”，确认状态文字和颜色仍在、聆听与整理动画停止。

Expected: 上述项目全部人工通过；真实 WebRTC 视频出现后静态海报隐藏，暂停/继续不会重新 seek 或叠出第二个视频。

- [ ] **Step 6: 先做一次浏览器 benchmark 冒烟**

使用 `backend\storage\runtime-ports.json` 的 `frontend_port` 打开游客端并附加 `?benchmark=1`，清空旧样本后完成一次真人语音提问。检查最新样本的 `marks_ms.first_valid_audio`、`marks_ms.first_visible_mouth` 和 `timings_ms.first_visible_mouth_ms` 均存在，且 `driver === "session_stream"`。

Expected: 单样本完整记录首个有效音频与首个可见口型；若任一字段缺失，先修复 ROI/benchmark 回归，不进入 30 次正式采样。

- [ ] **Step 7: 采集并验收严格端到端样本**

打开 `scripts\start.ps1 -KeepAlive` 输出的游客端地址并附加 `?benchmark=1`，在控制台先执行：

```js
window.__LINGJING_E2E_BENCHMARK__.clear()
```

在同一页面、同一预热 session 中完成 30 次真人语音提问，中途不刷新页面；第 1 次标为 cold，其余 29 次标为 hot。每条样本的 `driver` 必须为 `session_stream`。完成后检查并导出：

```js
window.__LINGJING_E2E_BENCHMARK__.getSamples().length
window.__LINGJING_E2E_BENCHMARK__.download()
```

Expected: 第一行返回 `30`；把下载文件保存为 `reports/quality/browser-e2e-samples.json`。随后运行：

```powershell
$env:COMPETITION_E2E_SAMPLE_FILE="reports/quality/browser-e2e-samples.json"
npm run competition-check
```

Expected: 只有当 30 个样本均包含真实 ASR、首段回答、真实 TTS、session 入队、首个有效音频和首个可见口型，`measurement_complete=true`、成功率为 100% 且 P95 小于 5000ms 时退出码才为 0。若未通过，表述为“严格端到端验收未完成或未达标”，并按报告的 `missing_stages`、`strict_failures` 与实际指标说明原因，不得把所有失败都归因于速度，也不得用单阶段耗时代替端到端结果。

- [ ] **Step 8: 最终报告边界检查**

确认后台和演示材料只作以下表述：界面已采用舞台留白；字幕与五态已实现；六项 WebRTC 检查证明真实视频轨、连续帧和可见嘴部运动；严格速度结论仅引用最新 30 次完整样本。表情部分只称“交互状态反馈、真实音频驱动口型和可见嘴部运动”；自然度只记录为本次演示视频的人工主观检查，不能写成模型质量、专家评价或量化结论。
