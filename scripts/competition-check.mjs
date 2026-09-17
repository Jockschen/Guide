import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const reportsDir = path.join(root, "reports");
const qualityDir = path.join(reportsDir, "quality");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const npmCliPath = process.env.npm_execpath && existsSync(process.env.npm_execpath)
  ? process.env.npm_execpath
  : "";
const pythonPath = path.join(root, ".venv", "Scripts", process.platform === "win32" ? "python.exe" : "python");

function isRealProvider(value) {
  const provider = String(value || "").trim().toLowerCase();
  return Boolean(provider) && provider !== "mock";
}

const REQUIRED_WEBRTC_CHECKS = [
  "video_track_received",
  "peer_connected",
  "speaking_state_seen",
  "enough_streamed_frames",
  "frames_are_not_frozen",
  "visible_mouth_motion",
];

function add(blockers, condition, message) {
  if (condition) blockers.push(message);
}

function requireFresh(ref, label, startedMs, blockers) {
  if (!ref || !ref.data) {
    blockers.push(`缺少 ${label} 报告`);
    return false;
  }
  if (!Number.isFinite(Number(ref.mtimeMs)) || Number(ref.mtimeMs) < startedMs) {
    blockers.push(`${label} 报告早于本次验收`);
    return false;
  }
  return true;
}

export function evaluateCompetitionEvidence(evidence) {
  const blockers = [];
  const warnings = [];
  const startedMs = Date.parse(evidence.startedAt || "");
  if (!Number.isFinite(startedMs)) {
    blockers.push("验收开始时间无效");
  }

  const selfCheckFresh = requireFresh(evidence.selfCheck, "self-check", startedMs, blockers);
  const selfCheck = evidence.selfCheck?.data || {};
  if (selfCheckFresh) {
    add(blockers, selfCheck.ok !== true, "self-check 离线回归失败");
    add(blockers, selfCheck.mode !== "offline-regression", "self-check 未标记为 offline-regression");
    add(blockers, selfCheck.competition_evidence !== false, "self-check 不得声明为比赛证据");
  }

  const liveFresh = requireFresh(evidence.liveCheck, "live-check", startedMs, blockers);
  const live = evidence.liveCheck?.data || {};
  const liveSummary = live.summary || {};
  if (evidence.liveCheck?.data) {
    add(blockers, live.ok !== true, "live-check 未通过");
    add(blockers, live.strict !== true, "live-check 必须使用 strict=true");
    add(blockers, Array.isArray(live.strict_failures) && live.strict_failures.length > 0, `live-check 严格失败：${(live.strict_failures || []).join("；")}`);
    add(blockers, liveSummary.qwen_configured !== true, "Qwen 未配置");
    add(blockers, liveSummary.competition_ready !== true, "competition_ready=false");
    add(blockers, liveSummary.knowledge_ready !== true, "本地知识库未就绪");
    add(blockers, !isRealProvider(liveSummary.asr_effective_provider), "ASR provider 缺失或仍处于 mock");
    add(blockers, !isRealProvider(liveSummary.tts_effective_provider), "TTS provider 缺失或仍处于 mock");
    add(
      blockers,
      !isRealProvider(liveSummary.asr_provider) || liveSummary.asr_text_ready !== true,
      "ASR 真实转写未返回非 mock provider 与有效文字",
    );
    add(blockers, liveSummary.opentalking_ready !== true, "OpenTalking 实时服务未就绪");
    add(blockers, liveSummary.pipeline_avatar_provider !== "opentalking", "数字人管线不是 OpenTalking");
    add(blockers, !isRealProvider(liveSummary.tts_provider) || liveSummary.tts_audio_ready !== true, "TTS 未返回真实音频");
  }

  const qaFresh = requireFresh(evidence.qa, "冻结 QA", startedMs, blockers);
  const qa = evidence.qa?.data || {};
  if (qaFresh) {
    const results = Array.isArray(qa.results) ? qa.results : [];
    add(blockers, Number(qa.total) < 17 || results.length < Number(qa.total || 0), "冻结 QA 未完整运行 17 题");
    add(blockers, Number(qa.accuracy_percent) < 90, "冻结 QA 本地准确率低于 90%");
    add(
      blockers,
      results.some((item) => /request-error|\(.*error|调用失败|网络连接失败/i.test(String(item.provider || "")) || item.error),
      "冻结 QA 包含请求失败或异常回退",
    );
    if (qa.official_evaluation !== true) warnings.push("冻结 QA 是本地自测，非比赛官方评测");
  }

  const hiddenQaFresh = requireFresh(evidence.hiddenQa, "隐藏 QA", startedMs, blockers);
  const hiddenQa = evidence.hiddenQa?.data || {};
  if (hiddenQaFresh) {
    const results = Array.isArray(hiddenQa.results) ? hiddenQa.results : [];
    add(blockers, Number(hiddenQa.total) < 30 || results.length < Number(hiddenQa.total || 0), "隐藏 QA 未完整运行至少 30 题");
    add(blockers, Number(hiddenQa.success_rate_percent) !== 100, "隐藏 QA 成功率未达到 100%");
    add(blockers, Number(hiddenQa.accuracy_percent) < 90, "隐藏 QA 本地准确率低于 90%");
    add(blockers, hiddenQa.official_evaluation !== false, "隐藏 QA 必须保持 official_evaluation=false 的本地自测边界");
    if (hiddenQa.official_evaluation === false) warnings.push("隐藏 QA 是本地自测，非比赛官方评测");
  }

  const webrtcFresh = requireFresh(evidence.webrtc, "WebRTC", startedMs, blockers);
  const webrtc = evidence.webrtc?.data || {};
  if (webrtcFresh) {
    const checks = webrtc.checks || {};
    const tracks = new Set(Array.isArray(webrtc.track_kinds) ? webrtc.track_kinds : []);
    add(blockers, webrtc.ok !== true, "WebRTC 验证未通过");
    add(blockers, !isRealProvider(webrtc.audio?.provider), "WebRTC 音频 provider 缺失或仍为 mock");
    add(blockers, !tracks.has("audio") || !tracks.has("video"), "WebRTC 未同时收到音视频轨");
    for (const key of REQUIRED_WEBRTC_CHECKS) {
      const message = key === "visible_mouth_motion"
        ? "WebRTC 未检测到可见口型运动：visible_mouth_motion"
        : `WebRTC 检查缺失或失败：${key}`;
      add(blockers, checks[key] !== true, message);
    }
    add(blockers, !Number.isFinite(Number(webrtc.latency_ms?.audio_to_visible_mouth_motion)), "WebRTC 缺少可见口型延迟");
  }

  const e2eFresh = requireFresh(evidence.e2e, "E2E", startedMs, blockers);
  const e2e = evidence.e2e?.data || {};
  if (e2eFresh) {
    const p95 = e2e.latency_ms?.p95 ?? e2e.p95_ms;
    add(blockers, e2e.measurement_complete !== true, "E2E measurement_complete=false");
    add(blockers, !Number.isFinite(Number(e2e.sample_count)) || Number(e2e.sample_count) < 30, "E2E 未完成至少 30 次真实运行");
    add(blockers, e2e.within_target !== true || !Number.isFinite(Number(p95)) || Number(p95) >= 5000, "E2E P95 缺失或未低于 5 秒");
    add(blockers, !Number.isFinite(Number(e2e.success_rate_percent)) || Number(e2e.success_rate_percent) < 100, "E2E 成功率缺失或未达到 100%");
  }

  return {
    ok: blockers.length === 0,
    blockers,
    warnings,
    evidence: {
      offline_regression: selfCheck.ok === true,
      self_check_competition_evidence: selfCheck.competition_evidence === true,
    },
  };
}

function run(command, args, label, env = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    env: { ...process.env, ...env },
    stdio: "inherit",
    shell: false,
  });
  if (result.status !== 0) {
    const detail = result.error?.message ? `: ${result.error.message}` : "";
    throw new Error(`${label} failed with exit code ${result.status}${detail}`);
  }
}

function runNpm(args, label, env = {}) {
  if (npmCliPath) return run(process.execPath, [npmCliPath, ...args], label, env);
  if (process.platform === "win32") {
    return run(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", npmCommand, ...args], label, env);
  }
  return run(npmCommand, args, label, env);
}

function readReport(relativePath) {
  const filePath = path.join(root, relativePath);
  if (!existsSync(filePath)) return null;
  return {
    data: JSON.parse(readFileSync(filePath, "utf-8")),
    mtimeMs: statSync(filePath).mtimeMs,
    path: filePath,
  };
}

function runStaticChecks() {
  const npmChecks = ["startup-audit", "copy-audit", "flow-audit", "admin-audit", "goal-audit", "typecheck", "build"];
  for (const script of npmChecks) runNpm(["run", script], script);
  run(pythonPath, ["-m", "unittest", "discover", "-s", "backend\\tests", "-p", "test_*.py"], "backend tests");
}

function resolveBaseUrl() {
  if (process.env.COMPETITION_BASE_URL) return process.env.COMPETITION_BASE_URL.replace(/\/$/, "");
  const runtimePath = path.join(root, "backend", "storage", "runtime-ports.json");
  if (!existsSync(runtimePath)) return "http://127.0.0.1:8000";
  const runtime = JSON.parse(readFileSync(runtimePath, "utf-8"));
  return String(runtime.api_base || runtime.backend || "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function resolveE2ESampleFile(argv = process.argv, env = process.env) {
  const inline = argv.find((value) => value.startsWith("--sample-file="));
  if (inline) return inline.slice("--sample-file=".length).trim();
  const index = argv.indexOf("--sample-file");
  if (index >= 0) return String(argv[index + 1] || "").trim();
  return String(env.COMPETITION_E2E_SAMPLE_FILE || "").trim();
}

export function buildE2EBenchmarkArgs(baseUrl, sampleFile = "") {
  const args = ["scripts\\benchmark_e2e.py", "--base-url", baseUrl];
  if (sampleFile) return [...args, "--sample-file", sampleFile];
  return [...args, "--samples", "30"];
}

function runLiveChecks(baseUrl, sampleFile = "") {
  runNpm(["run", "self-check"], "offline self-check");
  runNpm(["run", "live-check"], "strict live-check", {
    LIVE_CHECK_STRICT: "1",
    LIVE_CHECK_BASE_URL: baseUrl,
  });
  run(pythonPath, ["scripts\\evaluate_frozen_qa.py", "--base-url", baseUrl], "frozen QA");
  run(
    pythonPath,
    [
      "scripts\\evaluate_frozen_qa.py",
      "--base-url",
      baseUrl,
      "--fixture",
      "backend\\tests\\fixtures\\hidden_scenic_qa_v1.json",
      "--no-persist",
    ],
    "hidden QA",
  );

  const openTalkingPython = path.join(root, "third_party", "opentalking", ".venv", "Scripts", process.platform === "win32" ? "python.exe" : "python");
  run(openTalkingPython, ["scripts\\validate_opentalking_webrtc.py", "--base-url", baseUrl], "WebRTC validation");
  run(pythonPath, buildE2EBenchmarkArgs(baseUrl, sampleFile), "E2E benchmark");
}

export function collectCompetitionEvidence(startedAt) {
  return {
    startedAt,
    selfCheck: readReport("reports/self-check-latest.json"),
    liveCheck: readReport("reports/live-service-check-latest.json"),
    qa: readReport("reports/quality/frozen-qa-latest.json"),
    hiddenQa: readReport("reports/quality/hidden-qa-latest.json"),
    webrtc: readReport("reports/quality/opentalking-webrtc-latest.json"),
    e2e: readReport("reports/quality/e2e-latency-latest.json"),
  };
}

async function main() {
  const live = !process.argv.includes("--static");
  const startedAt = new Date().toISOString();
  let error = null;
  let result = { ok: false, blockers: [], warnings: [], evidence: {} };
  try {
    runStaticChecks();
    if (live) {
      runLiveChecks(resolveBaseUrl(), resolveE2ESampleFile());
      result = evaluateCompetitionEvidence(collectCompetitionEvidence(startedAt));
      if (!result.ok) throw new Error(result.blockers.join("；"));
    } else {
      result = {
        ok: true,
        blockers: [],
        warnings: ["仅完成静态验收；真实比赛链路需使用 --live"],
        evidence: { mode: "static" },
      };
    }
  } catch (caught) {
    error = caught instanceof Error ? caught.message : String(caught);
    if (!result.blockers.length) result.blockers = [error];
  }

  const report = {
    mode: live ? "competition-strict" : "competition-static",
    ok: !error && result.ok,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    blockers: result.blockers,
    warnings: result.warnings,
    evidence: result.evidence,
  };
  mkdirSync(reportsDir, { recursive: true });
  writeFileSync(path.join(reportsDir, "competition-check-latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf-8");
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.ok ? 0 : 1;
}

const isDirectRun = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isDirectRun) await main();
