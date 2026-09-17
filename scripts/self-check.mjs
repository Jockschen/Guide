import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const backendPort = Number(process.env.SELF_CHECK_BACKEND_PORT || 8041);
const frontendPort = Number(process.env.SELF_CHECK_FRONTEND_PORT || 3041);
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const pythonPath = path.join(root, ".venv", "Scripts", process.platform === "win32" ? "python.exe" : "python");
const selfCheckSpeechEnv = {
  ASR_PROVIDER: "mock",
  TTS_PROVIDER: "mock"
};
const report = {
  ok: false,
  mode: "offline-regression",
  competition_evidence: false,
  started_at: new Date().toISOString(),
  finished_at: "",
  checks: [],
  runtime: {},
  error: null
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function record(name, status, detail = {}) {
  report.checks.push({
    name,
    status,
    ...detail
  });
}

function run(command, args, label, options = {}) {
  console.log(label);
  const result = spawnSync(command, args, {
    cwd: root,
    env: { ...process.env, ...(options.env || {}) },
    stdio: "inherit",
    shell: Boolean(options.shell)
  });
  assert(result.status === 0, `${label} failed with exit code ${result.status}${result.error ? `: ${result.error.message}` : ""}`);
  record(label, "passed");
}

function start(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: root,
    env: { ...process.env, ...(options.env || {}) },
    stdio: ["ignore", "pipe", "pipe"],
    shell: Boolean(options.shell)
  });
  child.stdout.on("data", (chunk) => {
    const text = chunk.toString();
    if (/error|failed|ready|started|uvicorn|next/i.test(text)) process.stdout.write(text);
  });
  child.stderr.on("data", (chunk) => {
    const text = chunk.toString();
    if (/error|failed|traceback|ready|started|uvicorn|next/i.test(text)) process.stderr.write(text);
  });
  return child;
}

function stop(child) {
  if (!child || child.killed) return;
  if (process.platform === "win32" && child.pid) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  child.kill("SIGTERM");
}

async function waitFor(url, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.status >= 200 && response.status < 500) return response;
    } catch {
      // Keep waiting.
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  assert(response.ok, `${url} returned ${response.status}`);
  return response.json();
}

async function getText(url) {
  const response = await fetch(url, { cache: "no-store" });
  assert(response.ok, `${url} returned ${response.status}`);
  return response.text();
}

async function getPageAndBundleText(baseUrl, route) {
  const pageUrl = new URL(route, baseUrl).toString();
  const html = await getText(pageUrl);
  const assetRefs = new Set();
  for (const match of html.matchAll(/(?:src|href)="([^"]+\.js[^"]*)"/g)) {
    assetRefs.add(new URL(match[1], baseUrl).toString());
  }
  const assets = [];
  for (const assetUrl of assetRefs) {
    try {
      assets.push(await getText(assetUrl));
    } catch {
      // The HTML status check above is the hard gate; individual preloaded chunks
      // can be skipped if Next.js changes asset names during startup.
    }
  }
  return [html, ...assets].join("\n");
}

function assertTextIncludes(text, snippets, label) {
  for (const snippet of snippets) {
    assert(text.includes(snippet), `${label} does not include expected UI text: ${snippet}`);
  }
}

function assertTextExcludes(text, snippets, label) {
  for (const snippet of snippets) {
    assert(!text.includes(snippet), `${label} includes forbidden delivery text: ${snippet}`);
  }
}

function visibleHtmlText(html) {
  return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  assert(response.ok, `${url} returned ${response.status}`);
  return response.json();
}

async function postMockAudio(url) {
  const form = new FormData();
  form.append("file", new Blob([Buffer.from("abc")], { type: "audio/webm" }), "question.webm");
  const response = await fetch(url, { method: "POST", body: form });
  assert(response.ok, `${url} returned ${response.status}`);
  return response.json();
}

let backend = null;
let frontend = null;
let exitCode = 0;

try {
  assert(existsSync(pythonPath), "Missing .venv Python. Run start.bat once to install backend dependencies.");

  const npmOptions = { shell: process.platform === "win32" };
  run(npmCommand, ["run", "startup-audit"], "1/10 startup script audit", npmOptions);
  run(npmCommand, ["run", "typecheck"], "2/10 typecheck", npmOptions);
  run(npmCommand, ["run", "copy-audit"], "3/10 tourist copy audit", npmOptions);
  run(npmCommand, ["run", "flow-audit"], "4/10 tourist interaction flow audit", npmOptions);
  run(npmCommand, ["run", "goal-audit"], "5/10 goal acceptance audit", npmOptions);
  run(pythonPath, ["-m", "unittest", "discover", "-s", "backend\\tests", "-p", "test_*.py"], "6/10 backend tests", {
    env: selfCheckSpeechEnv
  });
  run(npmCommand, ["run", "build"], "7/10 production build", npmOptions);

  console.log("8/10 backend runtime checks");
  backend = start(pythonPath, ["-m", "uvicorn", "server.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", String(backendPort)], {
    env: { PYTHONPATH: path.join(root, "backend"), ...selfCheckSpeechEnv }
  });
  const backendBase = `http://127.0.0.1:${backendPort}`;
  await waitFor(`${backendBase}/api/health`, 45000);
  const health = await getJson(`${backendBase}/api/health`);
  assert(health.ok === true, "Backend health returned ok=false");
  assert(Boolean(health.asr_effective_provider), "ASR effective provider is empty");
  assert(Boolean(health.tts_effective_provider), "TTS effective provider is empty");
  record("backend health", "passed", {
    asr: health.asr_effective_provider,
    tts: health.tts_effective_provider,
    qwen_configured: Boolean(health.qwen_configured)
  });

  const pipeline = await getJson(`${backendBase}/api/admin/pipeline-check`);
  assert(pipeline.ok === true, "Pipeline check returned ok=false");
  assert(pipeline.data.knowledge_ready === true, "Pipeline check did not retrieve knowledge");
  assert(Number(pipeline.data.visemes_count) > 0, "Pipeline check did not generate visemes");
  record("pipeline check", "passed", {
    retrieved_chunks: pipeline.data.retrieved_chunks,
    visemes_count: pipeline.data.visemes_count,
    tts_effective_provider: pipeline.data.tts_effective_provider
  });

  const readiness = await getJson(`${backendBase}/api/admin/demo-readiness`);
  assert(readiness.ok === true, "Demo readiness returned ok=false");
  assert(Boolean(readiness.data.digital_human_plan), "Demo readiness did not return digital human plan");
  record("demo readiness", readiness.data.competition_ready ? "passed" : "informational", {
    competition_ready: Boolean(readiness.data.competition_ready),
    digital_human_plan: readiness.data.digital_human_plan,
    blockers: readiness.data.blockers
  });

  const tts = await postJson(`${backendBase}/api/tts/synthesize`, {
    text: "欢迎来到灵山胜境",
    voice: "gentle",
    style: "自然讲解",
    speed: 1,
    volume: 0.8
  });
  assert(tts.ok === true, "TTS endpoint returned ok=false");
  assert(Boolean(tts.data.provider), "TTS provider is empty");
  record("tts adapter", "passed", { provider: tts.data.provider, audio_ready: Boolean(tts.data.audio_url) });

  const asr = await postMockAudio(`${backendBase}/api/asr/transcribe`);
  assert(asr.ok === true, "ASR endpoint returned ok=false");
  assert(Boolean(String(asr.data.text || "").trim()), "ASR fallback text is empty");
  record("asr adapter", "passed", { provider: asr.data.provider, text_ready: true });

  console.log("9/10 frontend runtime checks");
  frontend = start(npmCommand, ["run", "start", "--", "--hostname", "127.0.0.1", "--port", String(frontendPort)], {
    shell: process.platform === "win32",
    env: {
      BACKEND_INTERNAL_URL: backendBase,
      NEXT_PUBLIC_API_BASE_URL: ""
    }
  });
  const frontendBase = `http://127.0.0.1:${frontendPort}`;
  await waitFor(frontendBase, 60000);
  const tourist = await fetch(frontendBase, { cache: "no-store" });
  assert(tourist.status === 200, "Tourist page did not return 200");
  const touristHtml = await tourist.text();
  assertTextExcludes(visibleHtmlText(touristHtml), ["管理中心"], "Tourist visible page HTML");
  record("tourist page", "passed", { http_status: tourist.status });
  const admin = await fetch(`${frontendBase}/admin`, { cache: "no-store" });
  assert(admin.status === 200, "Admin page did not return 200");
  record("admin page", "passed", { http_status: admin.status });
  const touristBundle = await getPageAndBundleText(frontendBase, "/");
  assertTextIncludes(touristBundle, ["灵境导游", "数字人导游", "音色", "风格", "语速", "音量", "字幕", "上传照片", "相机识景", "导游在线", "正在聆听", "正在整理", "正在讲解", "讲解已暂停"], "Tourist runtime bundle");
  assertTextExcludes(touristBundle, ["RTX4060", "RTX 4060", "Audio2Face", "生成口型中", "同步口型讲解", "口型链路异常"], "Tourist runtime bundle");
  const adminBundle = await getPageAndBundleText(frontendBase, "/admin");
  assertTextIncludes(adminBundle, ["景区运营中心", "运营概览", "知识内容", "数字人形象", "游客感受", "质量报告", "刷新"], "Admin runtime bundle");
  assertTextExcludes(adminBundle, ["RTX4060", "RTX 4060", "Audio2Face"], "Admin runtime bundle");
  record("frontend content bundle", "passed");
  const proxyPipeline = await getJson(`${frontendBase}/api/admin/pipeline-check`);
  assert(proxyPipeline.ok === true, "Frontend API proxy pipeline check failed");
  record("frontend api proxy", "passed");

  console.log("10/10 self-check complete");
  report.ok = true;
  report.runtime = {
    backend: backendBase,
    frontend: frontendBase,
    asr: health.asr_effective_provider,
    tts: health.tts_effective_provider,
    chunks: pipeline.data.retrieved_chunks,
    visemes: pipeline.data.visemes_count
  };
  console.log(JSON.stringify(report.runtime));
} catch (error) {
  exitCode = 1;
  report.error = error instanceof Error ? error.message : String(error);
  console.error(error instanceof Error ? error.stack || error.message : error);
} finally {
  stop(frontend);
  stop(backend);
  report.finished_at = new Date().toISOString();
  const reportDir = path.join(root, "reports");
  mkdirSync(reportDir, { recursive: true });
  writeFileSync(path.join(reportDir, "self-check-latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf-8");
}

process.exit(exitCode);
