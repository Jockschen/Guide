import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import * as competitionCheck from "../competition-check.mjs";

const { evaluateCompetitionEvidence } = competitionCheck;

const startedAt = "2026-07-13T02:00:00.000Z";
const fresh = Date.parse("2026-07-13T02:00:01.000Z");

function completeEvidence() {
  return {
    startedAt,
    selfCheck: {
      mtimeMs: fresh,
      data: {
        ok: true,
        mode: "offline-regression",
        competition_evidence: false,
        runtime: { asr: "mock", tts: "mock" },
      },
    },
    liveCheck: {
      mtimeMs: fresh,
      data: {
        ok: true,
        strict: true,
        strict_failures: [],
        summary: {
          qwen_configured: true,
          asr_effective_provider: "vivo",
          asr_provider: "vivo",
          asr_text_ready: true,
          tts_effective_provider: "edge",
          competition_ready: true,
          knowledge_ready: true,
          opentalking_ready: true,
          pipeline_avatar_provider: "opentalking",
          tts_provider: "edge",
          tts_audio_ready: true,
        },
      },
    },
    qa: {
      mtimeMs: fresh,
      data: {
        official_evaluation: false,
        total: 17,
        passed: 16,
        accuracy_percent: 94.12,
        results: Array.from({ length: 17 }, (_, index) => ({
          id: `qa-${index + 1}`,
          provider: index === 0 ? "local-faq" : "qwen",
          passed: index !== 16,
        })),
      },
    },
    hiddenQa: {
      mtimeMs: fresh,
      data: {
        official_evaluation: false,
        total: 30,
        passed: 27,
        accuracy_percent: 90,
        success_rate_percent: 100,
        results: Array.from({ length: 30 }, (_, index) => ({
          id: `hidden-${index + 1}`,
          provider: "qwen",
          passed: index < 27,
        })),
      },
    },
    webrtc: {
      mtimeMs: fresh,
      data: {
        ok: true,
        audio: { provider: "edge" },
        track_kinds: ["audio", "video"],
        checks: {
          video_track_received: true,
          peer_connected: true,
          speaking_state_seen: true,
          enough_streamed_frames: true,
          frames_are_not_frozen: true,
          visible_mouth_motion: true,
        },
        metrics: { speaking_unique_frames: 126, speaking_mouth_delta_max: 7.5 },
        latency_ms: { audio_to_visible_mouth_motion: 1149.1 },
      },
    },
    e2e: {
      mtimeMs: fresh,
      data: {
        official_evaluation: false,
        measurement_complete: true,
        within_target: true,
        measured_total_ms: 4200,
        sample_count: 30,
        success_rate_percent: 100,
        latency_ms: { p50: 3600, p95: 4800 },
      },
    },
  };
}

test("offline mock self-check is informational, not competition evidence", () => {
  const result = evaluateCompetitionEvidence(completeEvidence());

  assert.equal(result.ok, true);
  assert.equal(result.evidence.offline_regression, true);
  assert.equal(result.evidence.self_check_competition_evidence, false);
});

test("rejects stale or non-strict live evidence", () => {
  const evidence = completeEvidence();
  evidence.liveCheck.mtimeMs = Date.parse("2026-07-13T01:59:59.000Z");
  evidence.liveCheck.data.strict = false;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("live-check 报告早于本次验收")));
  assert(result.blockers.some((item) => item.includes("strict=true")));
});

test("requires competition-ready real speech and OpenTalking", () => {
  const evidence = completeEvidence();
  Object.assign(evidence.liveCheck.data.summary, {
    competition_ready: false,
    asr_effective_provider: "mock",
    tts_effective_provider: "mock",
    opentalking_ready: false,
    pipeline_avatar_provider: "demo",
    tts_audio_ready: false,
  });

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  for (const expected of ["competition_ready", "ASR", "TTS", "OpenTalking", "真实音频"]) {
    assert(result.blockers.some((item) => item.includes(expected)), expected);
  }
});

test("rejects incomplete or weak frozen QA evidence", () => {
  const evidence = completeEvidence();
  evidence.qa.data.total = 16;
  evidence.qa.data.accuracy_percent = 87.5;
  evidence.qa.data.results[0].provider = "request-error";

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("17 题")));
  assert(result.blockers.some((item) => item.includes("90%")));
  assert(result.blockers.some((item) => item.includes("请求失败")));
});

test("keeps local QA boundary as a warning", () => {
  const result = evaluateCompetitionEvidence(completeEvidence());

  assert.equal(result.ok, true);
  assert(result.warnings.some((item) => item.includes("非比赛官方评测")));
});

test("requires fresh hidden QA evidence with strict local thresholds", () => {
  const missing = completeEvidence();
  delete missing.hiddenQa;
  const missingResult = evaluateCompetitionEvidence(missing);
  assert.equal(missingResult.ok, false);
  assert(missingResult.blockers.some((item) => item.includes("隐藏 QA")));

  const weak = completeEvidence();
  Object.assign(weak.hiddenQa.data, {
    official_evaluation: true,
    total: 29,
    accuracy_percent: 89.9,
    success_rate_percent: 96,
  });
  weak.hiddenQa.data.results = weak.hiddenQa.data.results.slice(0, 29);
  const weakResult = evaluateCompetitionEvidence(weak);
  assert.equal(weakResult.ok, false);
  for (const expected of ["30 题", "100%", "90%", "official_evaluation=false"]) {
    assert(weakResult.blockers.some((item) => item.includes(expected)), expected);
  }
});

test("requires real WebRTC tracks, motion, and non-mock audio", () => {
  const evidence = completeEvidence();
  evidence.webrtc.data.audio.provider = "mock";
  evidence.webrtc.data.track_kinds = ["video"];
  evidence.webrtc.data.checks.visible_mouth_motion = false;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("WebRTC 音频")));
  assert(result.blockers.some((item) => item.includes("音视频轨")));
  assert(result.blockers.some((item) => item.includes("口型运动")));
});

test("requires complete 30-sample E2E evidence within five seconds", () => {
  const evidence = completeEvidence();
  Object.assign(evidence.e2e.data, {
    measurement_complete: false,
    within_target: false,
    sample_count: 1,
    latency_ms: { p50: 17739, p95: 17739 },
  });

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("measurement_complete")));
  assert(result.blockers.some((item) => item.includes("30 次")));
  assert(result.blockers.some((item) => item.includes("P95")));
});

test("rejects a complete report whose nested P95 exceeds five seconds", () => {
  const evidence = completeEvidence();
  evidence.e2e.data.within_target = true;
  evidence.e2e.data.latency_ms.p95 = 5001;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("P95")));
});

test("fails closed when live speech providers are missing", () => {
  const evidence = completeEvidence();
  delete evidence.liveCheck.data.summary.asr_effective_provider;
  delete evidence.liveCheck.data.summary.asr_provider;
  delete evidence.liveCheck.data.summary.tts_effective_provider;
  delete evidence.liveCheck.data.summary.tts_provider;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("ASR provider")));
  assert(result.blockers.some((item) => item.includes("TTS provider")));
});

test("requires a non-mock ASR smoke result with recognized text", () => {
  const evidence = completeEvidence();
  evidence.liveCheck.data.summary.asr_provider = "mock";
  evidence.liveCheck.data.summary.asr_text_ready = false;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("ASR 真实转写")));
});

test("fails closed when WebRTC audio provider or a fixed check is missing", () => {
  const evidence = completeEvidence();
  delete evidence.webrtc.data.audio.provider;
  delete evidence.webrtc.data.checks.frames_are_not_frozen;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("WebRTC 音频 provider")));
  assert(result.blockers.some((item) => item.includes("frames_are_not_frozen")));
});

test("fails closed when E2E success rate or P95 is missing", () => {
  const evidence = completeEvidence();
  delete evidence.e2e.data.success_rate_percent;
  delete evidence.e2e.data.latency_ms.p95;

  const result = evaluateCompetitionEvidence(evidence);

  assert.equal(result.ok, false);
  assert(result.blockers.some((item) => item.includes("成功率")));
  assert(result.blockers.some((item) => item.includes("P95")));
});

test("default package command is live and static mode is explicit", () => {
  const packageJson = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf-8"));

  assert.equal(packageJson.scripts["competition-check"], "node scripts/competition-check.mjs --live");
  assert.equal(packageJson.scripts["competition-check:static"], "node scripts/competition-check.mjs --static");
});

test("passes a CLI or environment sample file to the E2E benchmark", () => {
  assert.equal(typeof competitionCheck.resolveE2ESampleFile, "function");
  assert.equal(typeof competitionCheck.buildE2EBenchmarkArgs, "function");
  assert.equal(
    competitionCheck.resolveE2ESampleFile(
      ["node", "competition-check.mjs", "--sample-file", "browser.json"],
      { COMPETITION_E2E_SAMPLE_FILE: "environment.json" },
    ),
    "browser.json",
  );
  assert.deepEqual(
    competitionCheck.buildE2EBenchmarkArgs("http://127.0.0.1:8000", "browser.json"),
    ["scripts\\benchmark_e2e.py", "--base-url", "http://127.0.0.1:8000", "--sample-file", "browser.json"],
  );
});
