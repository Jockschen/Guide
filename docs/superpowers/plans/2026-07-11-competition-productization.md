# 灵境导游比赛级产品化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. All production changes start with a failing test or audit assertion and end with focused verification.

**Goal:** Deliver the selected “山水长卷” visitor experience, an official OpenTalking session/WebRTC primary path, and the missing admin/competition capabilities as one runnable system.

**Architecture:** Keep FastAPI as the product façade for Qwen, the local knowledge base, Vivo TTS, admin state, and quality evidence. Proxy OpenTalking’s official session/audio/WebRTC/event contract through this façade and render its media stream in the existing React client. Split the frontend into focused visitor guide, itinerary, streaming avatar, and admin-domain components while replacing the accumulated CSS patch stack with one tokenized shell.

**Tech Stack:** Next.js 15, React 19, TypeScript, FastAPI, SQLite, OpenTalking, QuickTalk, WebRTC, Vivo ASR/TTS, Qwen, Python unittest/pytest-style tests, Node audit scripts, headless Chrome visual capture.

## Global constraints

- Primary digital-human path is session + WebRTC; full MP4 is compatibility fallback only.
- Local profile is QuickTalk, 1280x720 or equivalent 720p canvas, 25fps, CUDA 0, prewarmed model/avatar, short audio chunks.
- Never describe the current synthetic still-image loop as a real neutral micro-motion template.
- Visitor avatar replacement is removed; camera/photo attachment remains only for multimodal questions.
- Route state persists across narration and mode changes.
- No technical provider/model names appear in visitor-facing states.
- The selected reference image is the visual truth; implementation and reference are compared at identical viewport and state.
- Existing user modifications in `third_party/opentalking` are preserved.
- This workspace has no functional Git metadata, so verification evidence is recorded under `reports/` instead of commit checkpoints.

## Task 1: Lock source-of-truth tests and design evidence

**Files:**
- Add: `backend/tests/test_opentalking_session_proxy.py`
- Add: `backend/tests/test_admin_competition_closure.py`
- Modify: `scripts/audit-tourist-flow.mjs`
- Add: `scripts/audit-admin-competition.mjs`
- Add: `reports/design-reference/selected-option-2-shanshui-scroll.png`

1. Assert the official session create, audio upload, WebRTC offer, event and interrupt boundaries.
2. Assert route mode switching, inline summary, persistence and explicit close behavior.
3. Assert digital-human profile publishing, knowledge edit/delete/reindex, textual feedback and quality-run APIs.
4. Run the focused tests/audits and save the expected failing output in `reports/test-evidence/`.

## Task 2: Implement the OpenTalking streaming façade

**Files:**
- Add: `backend/server/opentalking_session.py`
- Modify: `backend/server/main.py`
- Modify: `backend/server/schemas.py`
- Modify: `.env.example`
- Modify: `scripts/start.ps1`
- Add: `scripts/prewarm_opentalking.py`

1. Add a small typed client for official session create/delete, `speak_flashtalk_audio`, offer/answer, SSE events and interrupt.
2. Expose same-origin `/api/avatar/sessions/*` routes with timeouts, error normalization and no secret leakage.
3. Resolve the active published avatar/voice/persona into session creation and TTS defaults.
4. Add `session -> remote -> legacy_mp4 -> audio_only` capability reporting, with session preferred by default.
5. Start/prewarm the model and selected avatar from the one-click launcher when dependencies are available; report an actionable fallback when the official service cannot start.

## Task 3: Build the WebRTC visitor client and persistent itinerary

**Files:**
- Add: `components/useOpenTalkingSession.ts`
- Modify: `components/DigitalHuman.tsx`
- Modify: `components/TouristExperience.tsx`
- Add: `components/ItineraryPanel.tsx`

1. Create one session per visitor guide lifecycle and negotiate a receive-only WebRTC connection.
2. Upload each ready Vivo TTS audio clip to that session; allow the stream to provide both video and synchronized audio.
3. Interrupt stale playback when a new answer begins; close peer/session resources on unmount.
4. Fall back without blocking text/TTS when streaming is unavailable.
5. Render a compact itinerary summary inside the answer and a full `对话 / 当前游线` mode in the same guide panel.
6. Keep the current route until explicit close or replacement; “讲这一站” must narrate without clearing it.

## Task 4: Rebuild the visitor visual shell

**Files:**
- Modify: `app/globals.css`
- Modify: `components/TouristExperience.tsx`
- Modify: `components/DigitalHuman.tsx`
- Add generated scenic assets under: `public/assets/generated/`

1. Replace the layered visitor patches with named design tokens and a single responsive layout.
2. Match the selected 1440×1024 reference: panoramic landscape focus, large left digital human, restrained editorial navigation and a quiet right guide panel.
3. Use real scenic and portrait assets at measured crops; use the selected icon library rather than text glyphs or hand-built SVG.
4. Implement desktop, tablet and 390px mobile states plus reduced-motion and keyboard focus states.

## Task 5: Complete admin digital-human management

**Files:**
- Modify: `backend/server/db.py`
- Modify: `backend/server/schemas.py`
- Modify: `backend/server/main.py`
- Modify: `components/AdminConsole.tsx`
- Add focused admin components under: `components/admin/`

1. Migrate the digital-human configuration to versioned assets, appearance/clothing versions, voice, persona, source video, driver provider and published state.
2. Provide asset upload, voice preview, draft preview, publish and rollback-safe active resolution.
3. Wire the published voice/persona/avatar into Vivo TTS, session creation and visitor introduction.
4. Clearly label a still-image fallback versus a real neutral source-video avatar.

## Task 6: Complete knowledge and feedback operations

**Files:**
- Modify: `backend/server/db.py`
- Modify: `backend/server/main.py`
- Modify: `components/AdminConsole.tsx`
- Modify: `components/TouristExperience.tsx`

1. Add knowledge edit, delete and reindex APIs with index version/status reporting.
2. Add visitor text feedback and store sentiment, topics and handling state.
3. Add admin trend views, service suggestions, acknowledge/resolve actions and management notes.
4. Label every dashboard dataset by provenance.

## Task 7: Add reproducible quality reports

**Files:**
- Add: `backend/tests/fixtures/frozen_scenic_qa.json`
- Add: `scripts/evaluate_frozen_qa.py`
- Add: `scripts/benchmark_e2e.py`
- Add: `components/admin/QualityReports.tsx`

1. Freeze a scenic factual QA set derived only from the provided local knowledge materials.
2. Record question, expected evidence, answer, citation/source and pass/fail; report aggregate accuracy without claiming official certification.
3. Measure ASR, retrieval/LLM, TTS, session enqueue, first frame and total first response latency separately.
4. Store timestamped JSON plus a readable Markdown report; show the latest verified result in admin.

## Task 8: Correct acceptance documentation

**Files:**
- Modify: `docs/competition-requirements-audit.md`
- Modify: `docs/digital-human-setup.md`
- Modify: `README.md`

1. Replace overclaims with evidence-linked statuses.
2. Document the local QuickTalk profile, real source-video preparation, prewarm, remote provider seam and fallback order.
3. Publish a requirement-to-evidence matrix separating implemented/demo-ready from official-evaluation pending.

## Task 9: Verify the product end to end

1. Run focused backend tests, all backend tests, flow/admin audits, TypeScript checking and production build.
2. Start the actual one-click stack and verify HTTP health, session capability, visitor UI, admin UI and generated evidence endpoints.
3. Capture visitor/admin at 1440×1024 and visitor at 390×844 with the approved headless Chrome fallback.
4. Put the selected reference and implementation capture in the same comparison image; fix mismatches and repeat.
5. Write `design-qa.md` with the exact final result `passed` only when all rubric-blocking defects are resolved.

