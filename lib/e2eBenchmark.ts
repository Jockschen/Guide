export type E2EBenchmarkMark =
  | "recording_stop"
  | "asr_start"
  | "asr_done"
  | "chat_start"
  | "first_narration"
  | "tts_start"
  | "tts_done"
  | "audio_upload_start"
  | "audio_upload_ack"
  | "first_valid_audio"
  | "first_visible_mouth";

export const E2E_BENCHMARK_FAILURE = {
  newVoiceSample: "被新的语音样本中断",
  newQuestion: "被新的游客问题中断",
  timeout: "60 秒内未同时检测到有效音频与可见口型",
  pageClosed: "浏览器页面在样本完成前关闭",
  streamInterrupted: "问答流被中断",
  noNarration: "问答流结束前未产生首段讲解",
  streamFailed: "问答流失败",
  noTtsAudio: "首段 TTS 未返回真实音频",
  noSessionStream: "OpenTalking 未使用 session_stream",
  sessionUnavailable: "OpenTalking 实时服务未就绪",
  audioPlaybackFailed: "真实 TTS 音频未能播放",
  ttsTimeout: "首段 TTS 超时",
  browserRecognition: "浏览器内置语音识别不计入真实 ASR 验收",
  asrNoText: "真实 ASR 未返回有效文字",
  asrFailed: "真实 ASR 请求失败"
} as const;

export type E2EBenchmarkTrace = {
  sampleId: string;
  runKind: "cold" | "hot";
  marks: Partial<Record<E2EBenchmarkMark, number>>;
  asrProvider?: string;
  ttsProvider?: string;
  driver?: string;
  question?: string;
  failureReasons: string[];
  finalized: boolean;
};

export type E2EBenchmarkSample = {
  sample_id: string;
  run_kind: "cold" | "hot";
  source: "browser-session";
  success: boolean;
  failure_reason?: string;
  marks_ms: Partial<Record<E2EBenchmarkMark, number>>;
  timings_ms: Partial<Record<"asr_ms" | "chat_ms" | "tts_ms" | "session_enqueue_ms" | "first_valid_audio_ms" | "first_visible_mouth_ms", number>>;
  end_to_end_ms: number | null;
  question?: string;
  collected_at: string;
  asr_provider: string;
  tts_provider: string;
  driver: string;
};

type BenchmarkApi = {
  download(): void;
  getSamples(): E2EBenchmarkSample[];
  clear(): void;
};

declare global {
  interface Window {
    __LINGJING_E2E_BENCHMARK__?: BenchmarkApi;
  }
}

const STORAGE_KEY = "lingjing-e2e-browser-samples-v1";
const REQUIRED_MARKS: E2EBenchmarkMark[] = [
  "recording_stop",
  "asr_start",
  "asr_done",
  "chat_start",
  "first_narration",
  "tts_start",
  "tts_done",
  "audio_upload_start",
  "audio_upload_ack",
  "first_valid_audio",
  "first_visible_mouth"
];
let pageTraceCount = 0;

function currentTime() {
  return performance.now();
}

function rounded(value: number) {
  return Math.round(value * 100) / 100;
}

function duration(trace: E2EBenchmarkTrace, start: E2EBenchmarkMark, end: E2EBenchmarkMark) {
  const before = trace.marks[start];
  const after = trace.marks[end];
  return before === undefined || after === undefined ? undefined : rounded(Math.max(0, after - before));
}

function realProvider(value: string | undefined) {
  const provider = String(value || "").trim().toLowerCase();
  return Boolean(provider) && provider !== "mock";
}

function readSamples(): E2EBenchmarkSample[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function writeSamples(samples: E2EBenchmarkSample[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(samples));
}

export function isE2EBenchmarkEnabled() {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("benchmark") === "1";
}

export function installE2EBenchmarkApi() {
  if (!isE2EBenchmarkEnabled() || window.__LINGJING_E2E_BENCHMARK__) return;
  window.__LINGJING_E2E_BENCHMARK__ = {
    getSamples: () => structuredClone(readSamples()),
    clear: () => writeSamples([]),
    download: () => {
      const payload = JSON.stringify({ samples: readSamples() }, null, 2);
      const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `browser-e2e-samples-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    }
  };
}

export function createVoiceBenchmarkTrace(): E2EBenchmarkTrace | null {
  if (!isE2EBenchmarkEnabled()) return null;
  const index = pageTraceCount++;
  return {
    sampleId: `browser-${Date.now()}-${index + 1}`,
    runKind: index === 0 ? "cold" : "hot",
    marks: {},
    failureReasons: [],
    finalized: false
  };
}

export function markBenchmark(trace: E2EBenchmarkTrace | null, mark: E2EBenchmarkMark, at = currentTime()) {
  if (!trace || trace.finalized || trace.marks[mark] !== undefined) return;
  trace.marks[mark] = at;
}

export function setBenchmarkProviders(trace: E2EBenchmarkTrace | null, providers: { asr?: string; tts?: string }) {
  if (!trace || trace.finalized) return;
  if (providers.asr !== undefined) trace.asrProvider = providers.asr;
  if (providers.tts !== undefined) trace.ttsProvider = providers.tts;
}

export function setBenchmarkDriver(trace: E2EBenchmarkTrace | null, driver: string) {
  if (!trace || trace.finalized) return;
  trace.driver = driver;
}

export function setBenchmarkQuestion(trace: E2EBenchmarkTrace | null, question: string) {
  if (!trace || trace.finalized) return;
  trace.question = question.trim();
}

function buildSample(trace: E2EBenchmarkTrace): E2EBenchmarkSample {
  const recordingStop = trace.marks.recording_stop;
  const validAudio = trace.marks.first_valid_audio;
  const visibleMouth = trace.marks.first_visible_mouth;
  const responseReady = validAudio === undefined || visibleMouth === undefined
    ? undefined
    : Math.max(validAudio, visibleMouth);
  const endToEnd = recordingStop === undefined || responseReady === undefined
    ? undefined
    : rounded(Math.max(0, responseReady - recordingStop));
  const missingMarks = REQUIRED_MARKS.filter((mark) => trace.marks[mark] === undefined);
  const providerFailure = !realProvider(trace.asrProvider)
    ? "ASR provider 不是有效真实服务"
    : !realProvider(trace.ttsProvider)
      ? "TTS provider 不是有效真实服务"
      : trace.driver !== "session_stream"
        ? "数字人未使用 session_stream"
        : "";
  const reasons = [...trace.failureReasons, ...(providerFailure ? [providerFailure] : []), ...missingMarks.map((mark) => `缺少 ${mark}`)];
  return {
    sample_id: trace.sampleId,
    run_kind: trace.runKind,
    source: "browser-session",
    success: reasons.length === 0 && endToEnd !== undefined,
    ...(reasons.length ? { failure_reason: [...new Set(reasons)].join("；") } : {}),
    marks_ms: Object.fromEntries(Object.entries(trace.marks).map(([key, value]) => [key, rounded(value)])),
    timings_ms: {
      asr_ms: duration(trace, "asr_start", "asr_done"),
      chat_ms: duration(trace, "chat_start", "first_narration"),
      tts_ms: duration(trace, "tts_start", "tts_done"),
      session_enqueue_ms: duration(trace, "audio_upload_start", "audio_upload_ack"),
      first_valid_audio_ms: duration(trace, "audio_upload_ack", "first_valid_audio"),
      first_visible_mouth_ms: duration(trace, "audio_upload_ack", "first_visible_mouth")
    },
    end_to_end_ms: endToEnd ?? null,
    ...(trace.question ? { question: trace.question } : {}),
    collected_at: new Date().toISOString(),
    asr_provider: trace.asrProvider || "",
    tts_provider: trace.ttsProvider || "",
    driver: trace.driver || ""
  };
}

export function completeBenchmarkTrace(trace: E2EBenchmarkTrace | null) {
  if (!trace || trace.finalized || !isE2EBenchmarkEnabled()) return;
  trace.finalized = true;
  writeSamples([...readSamples(), buildSample(trace)]);
}

export function tryCompleteBenchmarkTrace(trace: E2EBenchmarkTrace | null) {
  if (!trace || trace.finalized) return;
  if (REQUIRED_MARKS.every((mark) => trace.marks[mark] !== undefined) && trace.driver) completeBenchmarkTrace(trace);
}

export function failBenchmarkTrace(trace: E2EBenchmarkTrace | null, reason: string) {
  if (!trace || trace.finalized) return;
  trace.failureReasons.push(reason);
  completeBenchmarkTrace(trace);
}
