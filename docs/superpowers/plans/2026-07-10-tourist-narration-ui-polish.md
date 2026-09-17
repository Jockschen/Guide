# Tourist Narration and UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tourist guide begin speaking as soon as audio is ready, improve QuickTalk render throughput, and turn the visitor-facing interface into a calm, polished guided-tour experience.

**Architecture:** Keep the real QuickTalk video path intact, but decouple it from initial narration. The browser starts the synthesized audio and live mouth-energy response immediately, submits real lip-sync work in parallel, and only blends in a ready video while the matching narration is still playing. Rendering remains locally cached and persistent; encoder and output-size controls reduce the time to a usable video.

**Tech Stack:** Next.js 15, React 19, TypeScript, FastAPI, Python, QuickTalk, FFmpeg, CSS.

## Global Constraints

- Tourist-facing copy must not disclose model names, provider names, render failures, internal states, or admin workflows.
- Never interrupt, restart, or duplicate the current audio while a real driver video becomes ready.
- Preserve real-video provenance: only a `real_video` driver may replace the live audio-driven stage.
- Keep the existing grounded scenic content and route behavior unchanged.
- Use 12--15fps and a 540px maximum encoded edge as the visitor-performance profile; validate that generated video remains playable.
- Maintain `prefers-reduced-motion` behavior and responsive support down to narrow mobile layouts.

---

### Task 1: Add a fast, configurable QuickTalk encode profile

**Files:**
- Modify: `scripts/opentalking_quicktalk_gpu_render.py`
- Modify: `.env.example`
- Modify: `backend/tests/test_opentalking_scripts.py`

**Interfaces:**
- Consumes: `OPENTALKING_QUICKTALK_FPS`, `OPENTALKING_QUICKTALK_MAX_SECONDS`.
- Produces: `OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE`, `OPENTALKING_QUICKTALK_X264_PRESET`, and output stats containing encoded dimensions.

- [ ] **Step 1: Add the failing source-contract test**

```python
source = (ROOT / "scripts" / "opentalking_quicktalk_gpu_render.py").read_text(encoding="utf-8")
self.assertIn("OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE", source)
self.assertIn("OPENTALKING_QUICKTALK_X264_PRESET", source)
self.assertIn("-preset", source)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `./.venv/Scripts/python.exe -m unittest backend.tests.test_opentalking_scripts`

- [ ] **Step 3: Implement the encode profile**

```python
def _downscale_frame(frame: np.ndarray, max_side: int) -> np.ndarray:
    height, width = frame.shape[:2]
    if max_side <= 0 or max(height, width) <= max_side:
        return frame
    scale = max_side / max(height, width)
    return cv2.resize(frame, (round(width * scale) // 2 * 2, round(height * scale) // 2 * 2), interpolation=cv2.INTER_AREA)
```

Apply this to every frame before opening FFmpeg, pass `-preset` from the environment and add `-movflags +faststart`. Document safe defaults in `.env.example`.

- [ ] **Step 4: Re-run the focused test**

Run: `./.venv/Scripts/python.exe -m unittest backend.tests.test_opentalking_scripts`

Expected: PASS.

### Task 2: Decouple immediate narration from background real-video rendering

**Files:**
- Modify: `components/TouristExperience.tsx`
- Modify: `components/DigitalHuman.tsx`
- Modify: `scripts/audit-tourist-flow.mjs`

**Interfaces:**
- Consumes: TTS `audio_url`, lipsync `video_url`, `DigitalHumanDriver` metadata.
- Produces: an audio-first playback state, a `driverTransition` visual state, and a safe `blendDriverVideo` path.

- [ ] **Step 1: Add failing interaction-audit assertions**

```js
assert(tourist.includes("void prepareDriverVideo("), "真实口型任务没有与音频播报并行启动。");
assert(tourist.includes("playAudioWithMouth(audio)"), "真实口型可用时没有先播放音频。 ");
assert(tourist.includes("blendDriverVideo("), "数字人缺少无中断视频切入逻辑。");
assert(!tourist.includes("正在生成口型视频"), "游客端仍暴露技术生成状态。");
```

- [ ] **Step 2: Run the interaction audit and verify failure**

Run: `npm run flow-audit`

- [ ] **Step 3: Implement audio-first orchestration**

```ts
const audio = new Audio(resolveMediaUrl(tts.audio_url));
activeAudioRef.current = audio;
await playAudioWithMouth(audio);
void prepareDriverVideo({ runId, text: speechText, audioUrl: tts.audio_url, audio });
```

`prepareDriverVideo` must ignore stale runs, only accept `real_video`, and call `blendDriverVideo` only when the matching audio is still playing with enough remaining duration. It must leave audio untouched and silently retain the live stage if the video is late or unavailable.

- [ ] **Step 4: Implement the blend boundary**

```ts
function blendDriverVideo(videoUrl: string, audio: HTMLAudioElement, runId: number) {
  setDriverVideoUrl(resolveMediaUrl(videoUrl));
  requestAnimationFrame(() => {
    const video = driverVideoRef.current;
    if (!video || speechRunIdRef.current !== runId) return;
    video.muted = true;
    video.currentTime = Math.min(Math.max(0, audio.currentTime), Math.max(0, video.duration - 0.1));
    void video.play();
  });
}
```

Do not pause `activeAudioRef`, call `speechSynthesis.cancel`, or replace the active audio event handlers.

- [ ] **Step 5: Update the digital-human state contract**

Replace technical labels with visitor language such as `正在讲解`, `讲解准备中`, and `导游在线`; use a `driverTransition` prop to crossfade the real driver video over the portrait without exposing the renderer.

- [ ] **Step 6: Re-run the interaction audit and typecheck**

Run: `npm run flow-audit; npm run typecheck`

Expected: both PASS.

### Task 3: Rewrite visitor-facing copy and hierarchy

**Files:**
- Modify: `components/TouristExperience.tsx`
- Modify: `components/DigitalHuman.tsx`
- Modify: `scripts/audit-tourist-copy.mjs`
- Modify: `scripts/audit-goal-acceptance.mjs`

**Interfaces:**
- Consumes: existing chat, route, media, and playback state.
- Produces: plain-language labels, refined action affordances, and audit rules that reject engineering terms.

- [ ] **Step 1: Add failing copy-audit cases**

```js
const forbiddenTerms = [
  "生成口型中", "同步口型讲解", "口型链路异常", "口型视频生成失败",
  "管理中心", "OpenTalking", "TTS", "ASR"
];
```

- [ ] **Step 2: Run the copy audit and verify failure**

Run: `npm run copy-audit`

- [ ] **Step 3: Replace tourist-facing status and navigation copy**

Use `灵境导游`, `正在为你讲解`, `讲解已准备好`, `我在听`, `换个问法试试`, and `新的导览` where appropriate. Remove the visitor-header admin link, retain admin access only at `/admin`, and simplify media controls into visitor-friendly labels.

- [ ] **Step 4: Update the acceptance audit to assert the new contract**

Replace obsolete string requirements in `scripts/audit-goal-acceptance.mjs` with `prepareDriverVideo`, `blendDriverVideo`, visitor-safe statuses, and no admin header link.

- [ ] **Step 5: Re-run copy and acceptance audits**

Run: `npm run copy-audit; npm run goal-audit`

Expected: both PASS.

### Task 4: Polish the visitor visual system and responsive states

**Files:**
- Modify: `app/globals.css`
- Modify: `components/DigitalHuman.tsx`
- Modify: `components/TouristExperience.tsx`

**Interfaces:**
- Consumes: existing CSS class names and component structure.
- Produces: smaller radii, restrained elevation, clear status treatments, responsive route panel, and motion-safe transitions.

- [ ] **Step 1: Consolidate visitor design tokens**

```css
:root {
  --radius-card: 14px;
  --radius-control: 10px;
  --surface-raised: #ffffff;
  --shadow-float: 0 8px 22px rgb(16 32 51 / 0.08);
  --ease-enter: cubic-bezier(0.16, 1, 0.3, 1);
}
```

- [ ] **Step 2: Replace excessive visual treatment**

Reduce 18--28px card radii, remove broad 70--90px decorative shadows, and keep one visual emphasis per interaction state. Give the avatar a stable stage, focused subtitle panel, and a crossfade that never hides content by default.

- [ ] **Step 3: Refine interactive and empty states**

Provide visible hover, focus-visible, disabled, active, loading, and empty-chat states. Ensure toolbar controls wrap without clipping and route stops remain reachable at 320px width.

- [ ] **Step 4: Add reduced-motion fallbacks**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 1ms !important; transition-duration: 1ms !important; }
  .avatar-video-driver { transition: opacity 120ms ease; }
}
```

- [ ] **Step 5: Build and inspect source-level responsive checks**

Run: `npm run typecheck; npm run build`

Expected: both PASS.

### Task 5: Verify the real path and record the improvement

**Files:**
- Modify: `README.md`
- Modify: `docs/opentalking-architecture-map.md`
- Modify: `scripts/self-check.mjs`

**Interfaces:**
- Consumes: running local frontend, backend, and OpenTalking bridge.
- Produces: documented fast-render profile and an auditable audio-first playback contract.

- [ ] **Step 1: Document the visitor experience and render profile**

State that narration begins with TTS audio, live stage motion is retained when real video is late, and true driver video blends in only without disrupting audio. Document output-size, FPS, and encoder knobs without exposing them in the tourist UI.

- [ ] **Step 2: Extend the static self-check contract**

Assert the new source strings and prohibit the retired technical states from visitor bundles.

- [ ] **Step 3: Run the full verification stack**

Run: `npm run startup-audit; npm run typecheck; npm run copy-audit; npm run flow-audit; npm run goal-audit; ./.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_*.py; npm run build`

Expected: all PASS.

- [ ] **Step 4: Measure a live short narration**

Record TTS time, lip-sync time, render frame count, encoded size, and whether QuickTalk remains persistent and warmed. Compare this to the pre-change 93-frame, 720px, 25fps baseline.

## Plan Self-Review

- Coverage: Tasks 1--2 cover real-video latency and audio continuity; Tasks 3--4 cover copy, UI, motion, responsive behavior, and visitor affordances; Task 5 covers documentation and proof.
- Placeholders: no deferred behavior or undefined API is required. New helpers stay inside `TouristExperience.tsx` to avoid a premature component split.
- Type consistency: `prepareDriverVideo` and `blendDriverVideo` consume the existing `DigitalHumanDriver`, `HTMLAudioElement`, and `speechRunIdRef` state.
- Repository note: this workspace does not expose usable Git metadata, so commit steps cannot be executed here.
