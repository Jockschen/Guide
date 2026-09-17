# Digital Human Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a verifiable digital-human driver decision layer so OpenTalking real video, demo video, and 2D audio-driven fallback are explicit and visible in the app.

**Architecture:** The backend owns driver truth and returns a small `driver` object with every lipsync result. The frontend stores this object and renders user-safe status labels without exposing technical provider names.

**Tech Stack:** Python FastAPI backend, React/Next.js frontend, TypeScript static checks, Node audit scripts, Python unittest.

## Global Constraints

- Only optimize digital-human behavior and documentation.
- Do not download or install large model weights.
- Do not present demo video as real-time lip sync.
- Do not expose ASR/TTS/OpenTalking provider names in visitor-facing copy.
- Use TDD for production-code changes.

---

### Task 1: Backend Driver Metadata

**Files:**
- Modify: `backend/tests/test_avatar.py`
- Modify: `backend/server/avatar.py`

**Interfaces:**
- Produces: `build_driver_metadata(provider: str, status: str, video_url: str = "", message: str = "") -> dict[str, Any]`
- Produces: every `request_lipsync()` result includes `driver`

- [ ] **Step 1: Write failing tests**

Add tests asserting:

```python
result = avatar.request_lipsync("欢迎来到灵山胜境", "/static/audio/test.wav")
self.assertEqual(result["driver"]["mode"], "real_video")
self.assertTrue(result["driver"]["video_playable"])
self.assertTrue(result["driver"]["claim_real_lipsync"])
```

Also assert demo returns `mode == "demo_video"` and fallback returns `mode == "audio_2d"`.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_avatar -v`
Expected: FAIL because `driver` is missing.

- [ ] **Step 3: Implement minimal metadata**

Add `build_driver_metadata()` in `backend/server/avatar.py` and attach it to every return path in `request_lipsync()` and `_demo_video_result()`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_avatar -v`
Expected: PASS.

### Task 2: Pipeline and Readiness Surfacing

**Files:**
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/server/main.py`

**Interfaces:**
- Consumes: `request_lipsync()` result `driver`
- Produces: `/api/admin/pipeline-check` includes `avatar_driver`
- Produces: `/api/admin/demo-readiness` includes `digital_human_driver_mode`

- [ ] **Step 1: Write failing tests**

Update pipeline tests to assert `avatar_driver.mode` exists and readiness exposes `digital_human_driver_mode`.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_pipeline -v`
Expected: FAIL before implementation.

- [ ] **Step 3: Implement minimal endpoint fields**

Add `avatar_driver` to pipeline-check data and `digital_human_driver_mode` to demo-readiness data.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_pipeline -v`
Expected: PASS.

### Task 3: Frontend Driver Consumption

**Files:**
- Modify: `lib/types.ts`
- Modify: `components/DigitalHuman.tsx`
- Modify: `components/TouristExperience.tsx`
- Modify: `scripts/audit-tourist-flow.mjs`
- Modify: `scripts/audit-goal-acceptance.mjs`

**Interfaces:**
- Consumes: lipsync response `driver`
- Produces: `DigitalHuman` prop `driverLabel`

- [ ] **Step 1: Write failing audit checks**

Update audits to require `driverLabel`, `avatarDriver`, and `lipsync.driver`.

- [ ] **Step 2: Run audit and verify RED**

Run: `npm run flow-audit`
Expected: FAIL because frontend does not consume driver metadata yet.

- [ ] **Step 3: Implement minimal frontend state**

Add `DigitalHumanDriver` type, keep `avatarDriver` state, set it from lipsync response, pass `driverLabel` to `DigitalHuman`, and remove eager demo playback before TTS.

- [ ] **Step 4: Run audit and typecheck**

Run: `npm run flow-audit`
Run: `npm run typecheck`
Expected: PASS.

### Task 4: Acceptance

**Files:**
- Modify only if earlier audits require docs or static checks.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest backend.tests.test_avatar backend.tests.test_pipeline -v
```

- [ ] **Step 2: Run static acceptance**

Run:

```powershell
npm run goal-audit
npm run typecheck
npm run build
```

- [ ] **Step 3: Run self-check if time permits**

Run:

```powershell
npm run self-check
```

Expected: Reports written under `reports/`, with digital-human driver metadata covered by tests and audits.
