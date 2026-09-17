import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const backendPort = Number(process.env.LIVE_CHECK_BACKEND_PORT || 8051);
const providedBaseUrl = process.env.LIVE_CHECK_BASE_URL || "";
const backendBase = providedBaseUrl || `http://127.0.0.1:${backendPort}`;
const strict = /^(1|true|yes|on)$/i.test(process.env.LIVE_CHECK_STRICT || "");
const pythonPath = path.join(root, ".venv", "Scripts", process.platform === "win32" ? "python.exe" : "python");
const report = {
  ok: false,
  strict,
  started_at: new Date().toISOString(),
  finished_at: "",
  backend: backendBase,
  checks: [],
  summary: {},
  strict_failures: []
};

function record(name, status, detail = {}) {
  report.checks.push({ name, status, ...detail });
}

function stop(child) {
  if (!child || child.killed) return;
  if (process.platform === "win32" && child.pid) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  child.kill("SIGTERM");
}

function startBackend() {
  if (providedBaseUrl) return null;
  if (!existsSync(pythonPath)) {
    throw new Error("Missing .venv Python. Run start.bat once before live-check.");
  }
  const child = spawn(
    pythonPath,
    ["-m", "uvicorn", "server.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", String(backendPort)],
    {
      cwd: root,
      env: { ...process.env, PYTHONPATH: path.join(root, "backend") },
      stdio: ["ignore", "pipe", "pipe"]
    }
  );
  child.stdout.on("data", (chunk) => {
    const text = chunk.toString();
    if (/error|failed|ready|started|uvicorn/i.test(text)) process.stdout.write(text);
  });
  child.stderr.on("data", (chunk) => {
    const text = chunk.toString();
    if (/error|failed|traceback|ready|started|uvicorn/i.test(text)) process.stderr.write(text);
  });
  return child;
}

async function fetchJson(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal, ...options });
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    if (!response.ok) {
      throw new Error(`${url} returned ${response.status}: ${text.slice(0, 240)}`);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function waitForHealth(timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      return await fetchJson(`${backendBase}/api/health`, {}, 3000);
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }
  throw new Error(`Timed out waiting for ${backendBase}/api/health: ${lastError}`);
}

async function probe(name, fn, required = false) {
  try {
    const data = await fn();
    record(name, "passed", { data });
    return data;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record(name, "failed", { message });
    if (strict && required) throw error;
    return null;
  }
}

async function postJson(url, body, timeoutMs = 15000) {
  return fetchJson(
    url,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    },
    timeoutMs
  );
}

function parsePcmWav(audioBytes) {
  if (
    audioBytes.length <= 44
    || audioBytes.subarray(0, 4).toString("ascii") !== "RIFF"
    || audioBytes.subarray(8, 12).toString("ascii") !== "WAVE"
  ) {
    throw new Error("TTS 结果不是有效 WAV，不能用于严格 ASR 验收");
  }
  let format = null;
  let pcmData = null;
  for (let offset = 12; offset + 8 <= audioBytes.length;) {
    const chunkId = audioBytes.subarray(offset, offset + 4).toString("ascii");
    const chunkSize = audioBytes.readUInt32LE(offset + 4);
    const chunkStart = offset + 8;
    const chunkEnd = chunkStart + chunkSize;
    if (chunkEnd > audioBytes.length) break;
    if (chunkId === "fmt " && chunkSize >= 16) {
      format = {
        encoding: audioBytes.readUInt16LE(chunkStart),
        channels: audioBytes.readUInt16LE(chunkStart + 2),
        sampleRate: audioBytes.readUInt32LE(chunkStart + 4),
        bitsPerSample: audioBytes.readUInt16LE(chunkStart + 14)
      };
    } else if (chunkId === "data") {
      pcmData = audioBytes.subarray(chunkStart, chunkEnd);
    }
    offset = chunkEnd + (chunkSize % 2);
  }
  if (!format || !pcmData || format.encoding !== 1 || format.channels !== 1 || format.bitsPerSample !== 16) {
    throw new Error("严格 ASR 验收要求单声道 16-bit PCM WAV");
  }
  return { ...format, pcmData };
}

function resamplePcm16Mono(pcmData, sourceRate, targetRate = 16000) {
  if (sourceRate === targetRate) return Buffer.from(pcmData);
  const sourceSamples = Math.floor(pcmData.length / 2);
  const targetSamples = Math.max(1, Math.floor(sourceSamples * targetRate / sourceRate));
  const output = Buffer.alloc(targetSamples * 2);
  for (let index = 0; index < targetSamples; index += 1) {
    const sourceIndex = Math.min(sourceSamples - 1, Math.floor(index * sourceRate / targetRate));
    output.writeInt16LE(pcmData.readInt16LE(sourceIndex * 2), index * 2);
  }
  return output;
}

async function transcribeGeneratedWav(audioUrl, asrProvider) {
  const resolvedAudioUrl = new URL(audioUrl, `${backendBase}/`).toString();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  let audioBytes;
  try {
    const response = await fetch(resolvedAudioUrl, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`${resolvedAudioUrl} returned ${response.status}`);
    audioBytes = Buffer.from(await response.arrayBuffer());
  } finally {
    clearTimeout(timer);
  }
  const wav = parsePcmWav(audioBytes);
  const vivo = String(asrProvider || "").trim().toLowerCase() === "vivo";
  const uploadBytes = vivo ? resamplePcm16Mono(wav.pcmData, wav.sampleRate) : audioBytes;
  const form = new FormData();
  form.append(
    "file",
    new Blob([uploadBytes], { type: vivo ? "audio/pcm" : "audio/wav" }),
    vivo ? "strict-asr-smoke.pcm" : "strict-asr-smoke.wav"
  );
  return fetchJson(
    `${backendBase}/api/asr/transcribe`,
    { method: "POST", body: form },
    30000
  );
}

let backend = null;
let exitCode = 0;

try {
  backend = startBackend();
  const health = await waitForHealth();
  record("health", "passed", {
    qwen_configured: Boolean(health.qwen_configured),
    asr: health.asr_effective_provider,
    tts: health.tts_effective_provider,
    opentalking_ready: Boolean(health.opentalking_ready),
    demo_video_ready: Boolean(health.demo_video_ready)
  });

  const readiness = await probe(
    "demo readiness",
    () => fetchJson(`${backendBase}/api/admin/demo-readiness`, {}, 8000),
    true
  );
  const pipeline = await probe(
    "knowledge to speech pipeline",
    () => fetchJson(`${backendBase}/api/admin/pipeline-check`, {}, 20000),
    strict
  );
  const tts = await probe(
    "tts synthesis",
    () =>
      postJson(
        `${backendBase}/api/tts/synthesize`,
        { text: "欢迎来到灵山胜境", voice: "gentle", style: "自然讲解", speed: 1, volume: 0.8 },
        20000
      ),
    strict && health.tts_effective_provider !== "mock"
  );

  const readinessData = readiness?.data || {};
  const pipelineData = pipeline?.data || {};
  const ttsData = tts?.data || {};
  const asr = strict && ttsData.audio_url
    ? await probe(
      "asr transcription",
      () => transcribeGeneratedWav(ttsData.audio_url, health.asr_effective_provider),
      false
    )
    : null;
  const asrData = asr?.data || {};
  if (readinessData.demo_video_ready) {
    await probe(
      "explicit demo lipsync",
      () =>
        postJson(
          `${backendBase}/api/avatar/lipsync`,
          { text: "欢迎来到灵山胜境", audio_url: null, allow_demo: true },
          8000
        ),
      false
    );
  }

  const strictFailures = [];
  if (strict && !health.qwen_configured) strictFailures.push("Qwen API Key 未配置");
  if (strict && health.asr_effective_provider === "mock") strictFailures.push("ASR 仍处于 mock 兜底");
  if (strict && health.tts_effective_provider === "mock") strictFailures.push("TTS 仍处于 mock 兜底");
  if (strict && readinessData.competition_ready !== true) {
    strictFailures.push(`competition_ready=false${Array.isArray(readinessData.blockers) && readinessData.blockers.length ? `：${readinessData.blockers.join("；")}` : ""}`);
  }
  if (strict && !health.opentalking_ready) strictFailures.push("OpenTalking 实时服务未就绪");
  if (strict && readinessData.knowledge_ready === false) strictFailures.push("资料库未完成同步");
  if (strict && pipelineData.avatar_provider !== "opentalking") strictFailures.push("数字人管线未使用 OpenTalking");
  if (strict && (ttsData.provider === "mock" || !ttsData.audio_url)) strictFailures.push("TTS 未返回真实音频");
  if (
    strict
    && (!String(asrData.provider || "").trim()
      || String(asrData.provider).trim().toLowerCase() === "mock"
      || !String(asrData.text || "").trim())
  ) {
    strictFailures.push("ASR 真实 WAV 转写未返回非 mock provider 与有效文字");
  }
  report.strict_failures = strictFailures;
  if (strictFailures.length > 0) {
    throw new Error(strictFailures.join("；"));
  }

  report.summary = {
    qwen_configured: Boolean(health.qwen_configured),
    asr_effective_provider: health.asr_effective_provider,
    asr_provider: asrData.provider || "",
    asr_text_ready: Boolean(String(asrData.text || "").trim()),
    tts_effective_provider: health.tts_effective_provider,
    competition_ready: readinessData.competition_ready === true,
    opentalking_ready: Boolean(health.opentalking_ready),
    demo_video_ready: Boolean(health.demo_video_ready),
    digital_human_plan: readinessData.digital_human_plan || "",
    knowledge_ready: Boolean(readinessData.knowledge_ready),
    tts_provider: ttsData.provider || "",
    tts_audio_ready: Boolean(ttsData.audio_url),
    pipeline_avatar_provider: pipelineData.avatar_provider || ""
  };
  report.ok = true;
  console.log(JSON.stringify(report.summary, null, 2));
} catch (error) {
  exitCode = 1;
  const message = error instanceof Error ? error.message : String(error);
  report.strict_failures = report.strict_failures.length ? report.strict_failures : [message];
  console.error(message);
} finally {
  stop(backend);
  report.finished_at = new Date().toISOString();
  const reportDir = path.join(root, "reports");
  mkdirSync(reportDir, { recursive: true });
  writeFileSync(path.join(reportDir, "live-service-check-latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf-8");
}

process.exit(exitCode);
