"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Camera, CameraOff, ImagePlus, Landmark, MapPinned, Mic, Pause, Play, Plus, Rocket, Route, Send, SlidersHorizontal, Square, Star, Volume2, X } from "lucide-react";
import { apiGet, apiPost, apiPostNdjson, API_BASE } from "@/lib/api";
import {
  createVoiceBenchmarkTrace,
  E2E_BENCHMARK_FAILURE,
  failBenchmarkTrace,
  installE2EBenchmarkApi,
  isE2EBenchmarkEnabled,
  markBenchmark,
  setBenchmarkDriver,
  setBenchmarkProviders,
  setBenchmarkQuestion,
  tryCompleteBenchmarkTrace,
  type E2EBenchmarkTrace
} from "@/lib/e2eBenchmark";
import type { ChatStreamEvent, ChatStreamProvider, DigitalHumanDriver, FAQ, Health, RoutePlan, SourceSnippet } from "@/lib/types";
import { DigitalHuman, type GuideStatus, type VisemeFrame } from "./DigitalHuman";
import { ItineraryPanel, ItinerarySummary } from "./ItineraryPanel";
import { useOpenTalkingSession } from "./useOpenTalkingSession";

type Message = {
  role: "user" | "assistant";
  text: string;
  sources?: SourceSnippet[];
  logId?: number;
  routePlan?: RoutePlan | null;
  mediaPreview?: string;
  mediaKind?: "image" | "camera";
  streamId?: number;
};

type TtsResult = {
  audio_url: string | null;
  provider: string;
  message: string;
  visemes?: VisemeFrame[];
};

type NarrationSegment = {
  id: number;
  text: string;
};

type GuideMode = "conversation" | "itinerary";

const GUIDE_STATUS = {
  online: "导游在线",
  listening: "正在聆听",
  thinking: "正在整理",
  speaking: "正在讲解",
  paused: "讲解已暂停"
} as const satisfies Record<string, GuideStatus>;

type PublishedProfile = {
  name?: string;
  persona?: string;
  voice?: string;
  avatar_asset_url?: string;
  clothing_asset_url?: string;
  status?: string;
  is_active?: boolean;
};

async function firstAudiblePcmOffsetMs(audioUrl: string) {
  try {
    const response = await fetch(audioUrl, { cache: "no-store" });
    if (!response.ok) return 0;
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 44 || String.fromCharCode(...bytes.slice(0, 4)) !== "RIFF") return 0;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let cursor = 12;
    let channels = 1;
    let sampleRate = 0;
    let bitsPerSample = 0;
    let dataOffset = 0;
    let dataLength = 0;
    while (cursor + 8 <= bytes.length) {
      const id = String.fromCharCode(...bytes.slice(cursor, cursor + 4));
      const length = view.getUint32(cursor + 4, true);
      const start = cursor + 8;
      if (id === "fmt " && start + 16 <= bytes.length) {
        channels = view.getUint16(start + 2, true);
        sampleRate = view.getUint32(start + 4, true);
        bitsPerSample = view.getUint16(start + 14, true);
      }
      if (id === "data") {
        dataOffset = start;
        dataLength = Math.min(length, bytes.length - start);
        break;
      }
      cursor = start + length + (length % 2);
    }
    if (!sampleRate || bitsPerSample !== 16 || !dataOffset || dataLength < 2) return 0;
    const frameBytes = Math.max(2, channels * 2);
    const frameCount = Math.floor(dataLength / frameBytes);
    for (let frame = 0; frame < frameCount; frame += 1) {
      let peak = 0;
      for (let channel = 0; channel < channels; channel += 1) {
        peak = Math.max(peak, Math.abs(view.getInt16(dataOffset + frame * frameBytes + channel * 2, true)));
      }
      if (peak >= 512) return frame / sampleRate * 1000;
    }
  } catch {
    // Unknown audio formats still require a real HTMLAudioElement playing event.
  }
  return 0;
}

function SuggestionIcon({ text }: { text: string }) {
  if (/(路线|怎么玩|游览|亲子|推荐)/.test(text)) return <Route size={18} />;
  if (/(文化|历史|寓意|特色)/.test(text)) return <Landmark size={18} />;
  return <MapPinned size={18} />;
}

const CHAT_STORAGE_KEY = "lingjing-tourist-chat-v2";

function userAgentHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash.toString(36);
}

type SpeechRecognitionCtor = new () => SpeechRecognition;

type SpeechRecognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: { [index: number]: { [index: number]: { transcript: string } } }; length: number }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type PcmRecorder = {
  stream: MediaStream;
  context: AudioContext;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  silence: GainNode;
  chunks: Float32Array[];
  inputSampleRate: number;
};

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
    webkitAudioContext?: typeof AudioContext;
  }
}

export function TouristExperience() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [speechPaused, setSpeechPaused] = useState(false);
  const [listening, setListening] = useState(false);
  const [subtitle, setSubtitle] = useState("");
  const [statusLabel, setStatusLabel] = useState<GuideStatus>(GUIDE_STATUS.online);
  const [voicePreset, setVoicePreset] = useState("published");
  const [guideStyle, setGuideStyle] = useState("自然讲解");
  const [speechRate, setSpeechRate] = useState(1);
  const [speechVolume, setSpeechVolume] = useState(0.86);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [visemes, setVisemes] = useState<VisemeFrame[]>([]);
  const [liveMouthLevel, setLiveMouthLevel] = useState(0.12);
  const [driverVideoUrl, setDriverVideoUrl] = useState<string | null>(null);
  const [driverPending, setDriverPending] = useState(false);
  const [avatarDriver, setAvatarDriver] = useState<DigitalHumanDriver | null>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [pendingImageBase64, setPendingImageBase64] = useState<string | null>(null);
  const [pendingMediaPreview, setPendingMediaPreview] = useState<string | null>(null);
  const [pendingMediaKind, setPendingMediaKind] = useState<"image" | "camera" | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [historyReady, setHistoryReady] = useState(false);
  const [visibleRoutePlan, setVisibleRoutePlan] = useState<RoutePlan | null>(null);
  const [guideMode, setGuideMode] = useState<GuideMode>("conversation");
  const [feedbackRatings, setFeedbackRatings] = useState<Record<number, number>>({});
  const [publishedProfile, setPublishedProfile] = useState<PublishedProfile | null>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [benchmarkEnabled, setBenchmarkEnabled] = useState(false);
  const [mouthMotionWatchToken, setMouthMotionWatchToken] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const pcmRecorderRef = useRef<PcmRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const cameraVideoElementRef = useRef<HTMLVideoElement | null>(null);
  const questionPreviewUrlsRef = useRef<string[]>([]);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const driverVideoRef = useRef<HTMLVideoElement | null>(null);
  const chatWindowRef = useRef<HTMLDivElement | null>(null);
  const speechRunIdRef = useRef(0);
  const streamRunIdRef = useRef(0);
  const chatAbortRef = useRef<AbortController | null>(null);
  const activeBenchmarkTraceRef = useRef<E2EBenchmarkTrace | null>(null);
  const openTalking = useOpenTalkingSession();
  const visitorMemoryKey = useMemo(() => {
    if (typeof window === "undefined") return CHAT_STORAGE_KEY;
    return `${CHAT_STORAGE_KEY}-${userAgentHash(window.navigator.userAgent || "browser")}`;
  }, []);

  useEffect(() => {
    const enabled = isE2EBenchmarkEnabled();
    setBenchmarkEnabled(enabled);
    if (enabled) installE2EBenchmarkApi();
  }, []);

  const handleFirstVisibleMouth = useCallback((at: number) => {
    const trace = activeBenchmarkTraceRef.current;
    if (!trace || trace.sampleId !== mouthMotionWatchToken) return;
    markBenchmark(trace, "first_visible_mouth", at);
    finishBenchmarkTraceIfReady(trace);
  }, [mouthMotionWatchToken]);

  function finishBenchmarkTraceIfReady(trace: E2EBenchmarkTrace | null) {
    if (!trace) return;
    tryCompleteBenchmarkTrace(trace);
    if (!trace.finalized) return;
    if (activeBenchmarkTraceRef.current === trace) activeBenchmarkTraceRef.current = null;
    setMouthMotionWatchToken(null);
  }

  function beginVoiceBenchmarkTrace() {
    const previous = activeBenchmarkTraceRef.current;
    if (previous && !previous.finalized) failBenchmarkTrace(previous, E2E_BENCHMARK_FAILURE.newVoiceSample);
    const trace = createVoiceBenchmarkTrace();
    if (!trace) return null;
    markBenchmark(trace, "recording_stop");
    activeBenchmarkTraceRef.current = trace;
    window.setTimeout(() => {
      if (!trace.finalized) failBenchmarkTrace(trace, E2E_BENCHMARK_FAILURE.timeout);
      if (activeBenchmarkTraceRef.current === trace) {
        activeBenchmarkTraceRef.current = null;
        setMouthMotionWatchToken(null);
      }
    }, 60_000);
    return trace;
  }

  useEffect(() => {
    if (!activeAudioRef.current) return;
    activeAudioRef.current.volume = speechVolume;
    activeAudioRef.current.playbackRate = speechRate;
  }, [speechRate, speechVolume]);

  useEffect(() => {
    const refreshHealth = () => {
      apiGet<Health>("/api/health").then(setHealth).catch(() => setHealth(null));
    };
    refreshHealth();
    const timer = window.setInterval(refreshHealth, 15000);
    apiGet<FAQ[]>("/api/faqs?limit=8").then(setFaqs).catch(() => setFaqs([]));
    apiGet<PublishedProfile>("/api/avatar/profile").then(setPublishedProfile).catch(() => setPublishedProfile(null));
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(visitorMemoryKey);
      if (stored) {
        const parsed = JSON.parse(stored) as Message[];
        if (Array.isArray(parsed)) {
          const restored = parsed.slice(-40);
          setMessages(restored);
          const restoredRoute = [...restored].reverse().find((message) => message.routePlan?.steps?.length)?.routePlan;
          if (restoredRoute) setVisibleRoutePlan(restoredRoute);
        }
      }
    } catch {
      // Local history is a convenience; ignore corrupted browser storage.
    } finally {
      setHistoryReady(true);
    }
  }, [visitorMemoryKey]);

  useEffect(() => {
    if (!historyReady) return;
    const storable = messages.slice(-40).map((message) => ({
      ...message,
      mediaPreview: undefined,
      mediaKind: undefined
    }));
    window.localStorage.setItem(visitorMemoryKey, JSON.stringify(storable));
  }, [historyReady, messages, visitorMemoryKey]);

  useEffect(() => {
    chatWindowRef.current?.scrollTo({ top: chatWindowRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, loading]);

  useEffect(() => {
    const chatWindow = chatWindowRef.current;
    const updateVisibility = () => {
      setShowScrollTop(window.scrollY > 360 || (chatWindow?.scrollTop ?? 0) > 420);
    };
    updateVisibility();
    window.addEventListener("scroll", updateVisibility, { passive: true });
    chatWindow?.addEventListener("scroll", updateVisibility, { passive: true });
    return () => {
      window.removeEventListener("scroll", updateVisibility);
      chatWindow?.removeEventListener("scroll", updateVisibility);
    };
  }, [historyReady]);

  useEffect(() => {
    const video = cameraVideoElementRef.current;
    if (!video) return;
    video.srcObject = cameraStream;
    if (cameraStream) {
      video.muted = true;
      video.playsInline = true;
      void video.play().catch(() => undefined);
    }
  }, [cameraStream]);

  useEffect(() => {
    return () => {
      questionPreviewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      activeAudioRef.current?.pause();
      driverVideoRef.current?.pause();
      chatAbortRef.current?.abort();
      failBenchmarkTrace(activeBenchmarkTraceRef.current, E2E_BENCHMARK_FAILURE.pageClosed);
      window.speechSynthesis?.cancel();
    };
  }, []);

  const presentationStatus: GuideStatus = listening ? GUIDE_STATUS.listening
    : speechPaused ? GUIDE_STATUS.paused
      : speaking ? GUIDE_STATUS.speaking
        : loading ? GUIDE_STATUS.thinking
          : statusLabel;

  const avatarExpression = presentationStatus === GUIDE_STATUS.listening
    ? "listening"
    : presentationStatus === GUIDE_STATUS.thinking
      ? "thinking"
      : presentationStatus === GUIDE_STATUS.speaking
        ? "speaking"
        : "friendly";
  const quickQuestions = useMemo(
    () => faqs.slice(0, 4).map((faq) => faq.question),
    [faqs]
  );
  const activeRoutePlan = visibleRoutePlan;
  const latestAssistantIndex = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === "assistant") return index;
    }
    return -1;
  }, [messages]);
  const followUpSuggestions = useMemo(
    () => buildFollowUpSuggestions(messages, quickQuestions, activeRoutePlan),
    [activeRoutePlan, messages, quickQuestions]
  );
  const starterSuggestions = useMemo(() => buildStarterSuggestions(quickQuestions), [quickQuestions]);
  const syntheticMotionEnabled = true;
  const publishedGuideName = publishedProfile?.name || "灵境导游";
  const publishedGuidePersona = publishedProfile?.persona || "熟悉景区、愿意耐心陪你游览的数字人导游";

  function updateStreamingAssistant(streamId: number, patch: Partial<Message>) {
    setMessages((items) => items.map((item) => item.streamId === streamId ? { ...item, ...patch } : item));
  }

  async function submit(nextQuestion = question, benchmarkTrace: E2EBenchmarkTrace | null = null) {
    const trimmed = nextQuestion.trim();
    if (!trimmed) return;
    const previousTrace = activeBenchmarkTraceRef.current;
    if (previousTrace && previousTrace !== benchmarkTrace && !previousTrace.finalized) {
      failBenchmarkTrace(previousTrace, E2E_BENCHMARK_FAILURE.newQuestion);
    }
    if (benchmarkTrace) {
      activeBenchmarkTraceRef.current = benchmarkTrace;
      setBenchmarkQuestion(benchmarkTrace, trimmed);
      markBenchmark(benchmarkTrace, "chat_start");
    }
    chatAbortRef.current?.abort();
    void openTalking.interrupt();
    stopSpeechPlayback(false);
    const controller = new AbortController();
    chatAbortRef.current = controller;
    const streamId = streamRunIdRef.current + 1;
    streamRunIdRef.current = streamId;
    const narrationRunId = speechRunIdRef.current + 1;
    speechRunIdRef.current = narrationRunId;
    const narrationQueue = createNarrationQueue(narrationRunId, benchmarkTrace);
    const routeRequested = shouldUpdateRoute(trimmed);
    const cameraFrame = !pendingImageBase64 && cameraStreamRef.current ? captureCameraFrame() : null;
    const requestImageBase64 = pendingImageBase64 ?? cameraFrame?.base64 ?? null;
    const mediaPreview = pendingMediaPreview ?? cameraFrame?.preview ?? undefined;
    const mediaKind = pendingMediaKind ?? (cameraFrame ? "camera" : undefined);
    setLoading(true);
    setStatusLabel(GUIDE_STATUS.thinking);
    setQuestion("");
    setPendingImageBase64(null);
    setPendingMediaPreview(null);
    setPendingMediaKind(null);
    setToolsOpen(false);
    setMessages((items) => [
      ...items,
      { role: "user", text: trimmed, mediaPreview, mediaKind },
      { role: "assistant", text: "", sources: [], streamId }
    ]);
    let answer = "";
    let sources: SourceSnippet[] = [];
    let provider: ChatStreamProvider = "qwen-stream";
    const routePromise = routeRequested
      ? apiPost<RoutePlan>("/api/route-plan", { interest: trimmed }).catch(() => null)
      : Promise.resolve(null);
    void routePromise.then((plan) => {
      if (controller.signal.aborted || !plan?.steps?.length) return;
      setVisibleRoutePlan(plan);
      setGuideMode("itinerary");
      updateStreamingAssistant(streamId, { routePlan: plan });
    });
    try {
      await apiPostNdjson<ChatStreamEvent>(
        "/api/chat/stream",
        {
          question: trimmed,
          image_base64: requestImageBase64 || undefined,
          guide_style: guideStyle,
          voice_preset: voicePreset
        },
        (event) => {
          if (controller.signal.aborted) return;
          const eventName = event.type || event.event;
          switch (eventName) {
            case "meta":
              provider = event.provider === "faq-fast-path"
                ? "faq-fast-path"
                : event.provider === "local-retrieval"
                  ? "local-retrieval"
                  : "qwen-stream";
              sources = event.sources || sources;
              updateStreamingAssistant(streamId, { sources });
              setStatusLabel(GUIDE_STATUS.thinking);
              break;
            case "delta": {
              const nextDelta = event.delta || event.text || "";
              answer += nextDelta;
              updateStreamingAssistant(streamId, { text: answer, sources });
              break;
            }
            case "narration":
              if (event.text) {
                markBenchmark(benchmarkTrace, "first_narration");
                narrationQueue.enqueueNarration(event.text);
              }
              break;
            case "done": {
              const finalAnswer = event.data?.answer || event.answer || answer;
              answer = finalAnswer;
              sources = event.data?.sources || event.sources || sources;
              updateStreamingAssistant(streamId, {
                text: finalAnswer,
                sources,
                logId: event.data?.log_id || event.log_id
              });
              narrationQueue.closeNarrationQueue();
              break;
            }
            case "error":
              narrationQueue.cancelNarrationQueue();
              throw new Error(event.message || "导览服务正在连接，请稍后重试。");
          }
        },
        controller.signal
      );
      if (benchmarkTrace && benchmarkTrace.marks.first_narration === undefined) {
        failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.noNarration);
      }
    } catch (error) {
      if (controller.signal.aborted) {
        failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.streamInterrupted);
        setMessages((items) => items.filter((item) => item.streamId !== streamId || item.text.trim()));
        return;
      }
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.streamFailed);
      narrationQueue.cancelNarrationQueue();
      stopSpeechPlayback(false);
      const text = error instanceof Error ? error.message : "导览服务正在连接，请稍后重试。";
      updateStreamingAssistant(streamId, { text });
      setSubtitle(text);
      setStatusLabel(GUIDE_STATUS.online);
    } finally {
      if (chatAbortRef.current === controller) {
        chatAbortRef.current = null;
        setLoading(false);
      }
    }
  }

  function shouldUpdateRoute(text: string) {
    return /路线|规划|半日|一日|行程|怎么走|游览安排|亲子|带孩子|家庭路线|历史文化路线|自然风光路线|拍照路线|慢游/.test(text)
      || (/我喜欢|感兴趣|偏好/.test(text) && /历史|文化|自然|风光|佛教|建筑|拍照/.test(text));
  }

  function createNarrationQueue(runId: number, benchmarkTrace: E2EBenchmarkTrace | null) {
    const pending: string[] = [];
    const seen = new Set<string>();
    const runtimeHealth = apiGet<Health>("/api/health").catch(() => health);
    let prefetched: { text: string; audio: Promise<TtsResult | null> } | null = null;
    let draining = false;
    let closed = false;
    let cancelled = false;

    function prefetchNext() {
      if (cancelled || prefetched || pending.length === 0) return;
      const text = pending.shift()!;
      prefetched = { text, audio: requestNarrationAudio(text, benchmarkTrace).catch(() => null) };
    }

    async function drainNarrationQueue() {
      if (draining || cancelled) return;
      draining = true;
      try {
        while (!cancelled && speechRunIdRef.current === runId) {
          prefetchNext();
          const current = prefetched;
          if (!current) break;
          prefetched = null;
          const tts = await current.audio;
          prefetchNext();
          const completed = await playNarrationSegment(current.text, tts, runId, runtimeHealth, benchmarkTrace);
          if (!completed) {
            cancelled = true;
            pending.length = 0;
            prefetched = null;
          }
        }
      } finally {
        draining = false;
        if (!cancelled && (prefetched || pending.length)) {
          void drainNarrationQueue();
        } else if (!cancelled && closed && speechRunIdRef.current === runId) {
          finishSpeechPlayback();
        }
      }
    }

    function enqueueNarration(text: string) {
      const segments = splitNarrationSegments(normalizeSpeechText(text));
      for (const segment of segments) {
        if (!segment.text || seen.has(segment.text)) continue;
        seen.add(segment.text);
        pending.push(segment.text);
      }
      if (!pending.length && !prefetched) return;
      setSpeaking(true);
      setSpeechPaused(false);
      setDriverPending(false);
      setStatusLabel(GUIDE_STATUS.thinking);
      prefetchNext();
      void drainNarrationQueue();
    }

    function closeNarrationQueue() {
      closed = true;
      if (!draining && !prefetched && pending.length === 0 && speechRunIdRef.current === runId) {
        finishSpeechPlayback();
      }
    }

    function cancelNarrationQueue() {
      cancelled = true;
      pending.length = 0;
      prefetched = null;
    }

    return { enqueueNarration, closeNarrationQueue, cancelNarrationQueue };
  }

  async function playNarrationSegment(
    text: string,
    tts: TtsResult | null,
    runId: number,
    runtimeHealthPromise: Promise<Health | null>,
    benchmarkTrace: E2EBenchmarkTrace | null
  ) {
    if (speechRunIdRef.current !== runId) return true;
    if (!tts?.audio_url) {
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.noTtsAudio);
      browserSpeak(text);
      return false;
    }
    const runtimeHealth = await runtimeHealthPromise;
    if (speechRunIdRef.current !== runId) return true;
    if (runtimeHealth) setHealth(runtimeHealth);
    const opentalkingReady = Boolean(runtimeHealth?.opentalking_ready);
    if (tts.visemes?.length) setVisemes(tts.visemes);
    else setVisemes(makeLocalVisemes(text));
    const mediaUrl = resolveMediaUrl(tts.audio_url);
    const audio = new Audio(mediaUrl);
    audio.volume = speechVolume;
    audio.playbackRate = speechRate;
    if (benchmarkTrace) {
      const audibleOffset = firstAudiblePcmOffsetMs(mediaUrl);
      audio.addEventListener("playing", () => {
        void audibleOffset.then((offsetMs) => {
          const delay = Math.max(0, offsetMs / Math.max(0.1, audio.playbackRate));
          window.setTimeout(() => {
            markBenchmark(benchmarkTrace, "first_valid_audio", performance.now());
            finishBenchmarkTraceIfReady(benchmarkTrace);
          }, delay);
        });
      }, { once: true });
    }
    activeAudioRef.current = audio;
    setDriverVideoUrl(null);
    setAvatarDriver(null);
    setSubtitle(text);
    setStatusLabel(GUIDE_STATUS.speaking);
    const streamed = await openTalking.enqueueAudio(mediaUrl, {
      onUploadStart: (at) => {
        markBenchmark(benchmarkTrace, "audio_upload_start", at);
        if (benchmarkTrace && !benchmarkTrace.finalized) setMouthMotionWatchToken(benchmarkTrace.sampleId);
      },
      onUploadAck: (at) => markBenchmark(benchmarkTrace, "audio_upload_ack", at),
      onFailure: (reason) => failBenchmarkTrace(benchmarkTrace, reason)
    });
    if (speechRunIdRef.current !== runId) return true;
    setDriverPending(!streamed && opentalkingReady);
    if (streamed) {
      setBenchmarkDriver(benchmarkTrace, "session_stream");
      finishBenchmarkTraceIfReady(benchmarkTrace);
      setAvatarDriver({
        mode: "real_video",
        label: "实时讲解",
        claim: "session_stream",
        status: "streaming",
        video_playable: true,
        claim_real_lipsync: true
      });
    } else if (opentalkingReady) {
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.noSessionStream);
      void prepareDriverVideo({ runId, text, audioUrl: tts.audio_url, audio });
    } else {
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.sessionUnavailable);
    }
    const outcome = await playAudioWithMouth(audio);
    if (speechRunIdRef.current !== runId) return true;
    activeAudioRef.current = null;
    setDriverVideoUrl(null);
    setAvatarDriver(null);
    setDriverPending(false);
    if (outcome === "error") {
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.audioPlaybackFailed);
      browserSpeak(text);
      return false;
    }
    return true;
  }

  async function requestNarrationAudio(text: string, benchmarkTrace: E2EBenchmarkTrace | null) {
    markBenchmark(benchmarkTrace, "tts_start");
    const result = await withTimeout(
      apiPost<TtsResult>("/api/tts/synthesize", {
        text,
        voice: voicePreset,
        style: guideStyle,
        speed: speechRate,
        volume: speechVolume
      }),
      60000
    );
    if (!result) {
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.ttsTimeout);
      return null;
    }
    markBenchmark(benchmarkTrace, "tts_done");
    setBenchmarkProviders(benchmarkTrace, { tts: result.provider });
    return result;
  }

  function resolveMediaUrl(value: string | null | undefined) {
    if (!value) return "";
    if (value.startsWith("http")) return value;
    if (value.startsWith("/")) return `${API_BASE}${value}`;
    return `${API_BASE}/${value}`;
  }

  async function prepareDriverVideo({
    runId,
    text,
    audioUrl,
    audio
  }: {
    runId: number;
    text: string;
    audioUrl: string;
    audio: HTMLAudioElement;
  }) {
    try {
      const lipsync = await withTimeout(
        apiPost<{ provider: string; status: string; visemes?: VisemeFrame[]; video_url?: string | null; driver?: DigitalHumanDriver }>("/api/avatar/lipsync", {
          text,
          audio_url: audioUrl,
          allow_demo: false
        }),
        120000
      );
      if (speechRunIdRef.current !== runId || activeAudioRef.current !== audio) return;
      if (!lipsync?.video_url || lipsync.driver?.mode !== "real_video") return;
      if (!blendDriverVideo(lipsync.video_url, audio, runId)) return;
      if (lipsync.driver) setAvatarDriver({ ...lipsync.driver, label: "讲解画面" });
      if (lipsync.visemes?.length) setVisemes(lipsync.visemes);
    } catch {
      // The live stage and narration remain available when a visual segment arrives late.
    } finally {
      if (speechRunIdRef.current === runId && activeAudioRef.current === audio) {
        setDriverPending(false);
      }
    }
  }

  function blendDriverVideo(value: string | null | undefined, audio: HTMLAudioElement, runId: number) {
    const videoSrc = resolveMediaUrl(value);
    const remaining = Number.isFinite(audio.duration) ? audio.duration - audio.currentTime : 0;
    if (!videoSrc || audio.paused || audio.ended || remaining < 0.85) return false;
    setDriverVideoUrl(videoSrc);
    window.setTimeout(() => {
      if (speechRunIdRef.current !== runId || activeAudioRef.current !== audio || audio.paused || audio.ended) return;
      const video = driverVideoRef.current;
      if (!video) return;
      video.muted = true;
      const startAtAudioPosition = () => {
        if (speechRunIdRef.current !== runId || activeAudioRef.current !== audio || audio.paused || audio.ended) return;
        if (!Number.isFinite(video.duration) || video.duration <= 0) return;
        video.currentTime = Math.min(audio.currentTime, Math.max(0, video.duration - 0.1));
        void video.play().catch(() => {
          if (speechRunIdRef.current === runId && activeAudioRef.current === audio) setDriverVideoUrl(null);
        });
      };
      video.onloadedmetadata = startAtAudioPosition;
      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) startAtAudioPosition();
    }, 100);
    return true;
  }

  function toggleSpeechPlayback() {
    if (!speaking && !speechPaused) return;
    const audio = activeAudioRef.current;
    if (audio) {
      if (speechPaused || audio.paused) {
        void audio.play().then(() => {
            const driverVideo = driverVideoRef.current;
            if (driverVideoUrl && driverVideo) {
              if (Number.isFinite(driverVideo.duration) && driverVideo.duration > 0) {
                driverVideo.currentTime = Math.min(audio.currentTime, Math.max(0, driverVideo.duration - 0.1));
                driverVideo.play().catch(() => undefined);
              }
          }
          setSpeechPaused(false);
          setStatusLabel(GUIDE_STATUS.speaking);
        }).catch(() => undefined);
      } else {
        audio.pause();
        driverVideoRef.current?.pause();
        setSpeechPaused(true);
        setLiveMouthLevel(0.12);
        setStatusLabel(GUIDE_STATUS.paused);
      }
      return;
    }
    if (!("speechSynthesis" in window)) return;
    if (speechPaused) {
      window.speechSynthesis.resume();
      driverVideoRef.current?.play().catch(() => undefined);
      setSpeechPaused(false);
      setStatusLabel(GUIDE_STATUS.speaking);
    } else {
      window.speechSynthesis.pause();
      driverVideoRef.current?.pause();
      setSpeechPaused(true);
      setLiveMouthLevel(0.12);
      setStatusLabel(GUIDE_STATUS.paused);
    }
  }

  function stopSpeechPlayback(resetStatus = true, cancelPending = true) {
    if (cancelPending) speechRunIdRef.current += 1;
    if (cancelPending) void openTalking.interrupt();
    activeAudioRef.current?.pause();
    activeAudioRef.current = null;
    const driverVideo = driverVideoRef.current;
    if (driverVideo) {
      driverVideo.pause();
      driverVideo.onended = null;
      driverVideo.onerror = null;
    }
    setDriverVideoUrl(null);
    setDriverPending(false);
    setAvatarDriver(null);
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
    setSpeechPaused(false);
    setLiveMouthLevel(0.12);
    if (resetStatus) setStatusLabel(GUIDE_STATUS.online);
  }

  function finishSpeechPlayback() {
    activeAudioRef.current = null;
    setDriverVideoUrl(null);
    setDriverPending(false);
    setAvatarDriver(null);
    setSpeaking(false);
    setSpeechPaused(false);
    setLiveMouthLevel(0.12);
    setStatusLabel(GUIDE_STATUS.online);
  }

  function normalizeSpeechText(text: string) {
    const cleanMarkdown = normalizeAssistantMarkdown(text)
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/[*_`>#]/g, "")
      .replace(/\s{2,}/g, " ");
    return cleanMarkdown
      .replace(/(\d{1,2})[:：](\d{2})\s*(?:-|~|—|–|到|至)\s*(\d{1,2})[:：](\d{2})/g, (_match, startHour, startMinute, endHour, endMinute) => {
        return `${formatClockTime(startHour, startMinute)}到${formatClockTime(endHour, endMinute)}`;
      })
      .replace(/(\d{1,2})[:：](\d{2})/g, (_match, hour, minute) => formatClockTime(hour, minute))
      .replace(/\s+([，。！？；：])/g, "$1")
      .trim();
  }

  function splitNarrationSegments(text: string, maxChars = 46): NarrationSegment[] {
    const sentences = text.match(/[^。！？]+[。！？]?/gu) || [text];
    const segments: string[] = [];
    let buffer = "";
    const flush = () => {
      const value = buffer.trim();
      if (value) segments.push(value);
      buffer = "";
    };
    for (const sentence of sentences) {
      const clauses = sentence.match(/[^，、；：]+[，、；：]?/gu) || [sentence];
      for (const rawClause of clauses) {
        const clause = rawClause.trim();
        if (!clause) continue;
        if (buffer && buffer.length + clause.length > maxChars) flush();
        if (clause.length <= maxChars) {
          buffer += clause;
          continue;
        }
        for (let start = 0; start < clause.length; start += maxChars) {
          const chunk = clause.slice(start, start + maxChars);
          if (buffer) flush();
          segments.push(chunk);
        }
      }
      if (buffer.length >= Math.round(maxChars * 0.62)) flush();
    }
    flush();
    return segments.slice(0, 6).map((segment, id) => ({ id, text: segment }));
  }

  function makeSubtitleText(text: string) {
    const clean = normalizeSpeechText(text)
      .replace(/资料依据[：:]?.*$/s, "")
      .replace(/建议顺序[：:]?/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (clean.length <= 180) return clean;
    const firstSentence = clean.match(/^.*?[。！？]/)?.[0];
    return firstSentence && firstSentence.length <= 180 ? firstSentence : clean.slice(0, 180);
  }

  function normalizeAssistantMarkdown(text: string) {
    return text
      .replace(/\\n/g, "\n")
      .replace(/<\s*details[^>]*>[\s\S]*?<\s*\/\s*details\s*>/gi, "")
      .replace(/<\s*br\s*\/?\s*>/gi, "\n")
      .replace(/<\s*details\s*>/gi, "")
      .replace(/<\s*\/\s*details\s*>/gi, "")
      .replace(/<\s*summary\s*>\s*(.*?)\s*<\s*\/\s*summary\s*>/gis, "**$1**\n\n")
      .replace(/<\/?\w+[^>]*>/g, "")
      .replace(/\\([#*_`[\]()])/g, "$1")
      .replace(/^>\s*资料依据[：:].*$/gm, "")
      .replace(/^\s*资料依据[：:].*$/gm, "")
      .replace(/^\s*来源[：:].*$/gm, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function formatClockTime(hourText: string, minuteText: string) {
    const hour = Number(hourText);
    const minute = Number(minuteText);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return `${hourText}点${minuteText}分`;
    const hourLabel = `${numberToChinese(hour)}点`;
    if (minute === 0) return hourLabel;
    const minuteLabel = minute < 10 && minuteText.startsWith("0")
      ? `零${numberToChinese(minute)}`
      : numberToChinese(minute);
    return `${hourLabel}${minuteLabel}分`;
  }

  function numberToChinese(value: number) {
    const digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
    const number = Math.max(0, Math.min(99, Math.trunc(value)));
    if (number < 10) return digits[number];
    if (number === 10) return "十";
    if (number < 20) return `十${digits[number % 10]}`;
    const tens = Math.floor(number / 10);
    const ones = number % 10;
    return `${digits[tens]}十${ones ? digits[ones] : ""}`;
  }

  async function playAudioWithMouth(audio: HTMLAudioElement): Promise<"ended" | "error"> {
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) {
      return new Promise((resolve) => {
        audio.onended = () => resolve("ended");
        audio.onerror = () => resolve("error");
        void audio.play().catch(() => resolve("error"));
      });
    }
    return new Promise((resolve) => {
      const context = new AudioContextCtor();
      const source = context.createMediaElementSource(audio);
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(context.destination);
      const samples = new Uint8Array(analyser.frequencyBinCount);
      let raf = 0;
      let settled = false;
      let tracking = false;
      const finish = (outcome: "ended" | "error") => {
        if (settled) return;
        settled = true;
        window.cancelAnimationFrame(raf);
        setLiveMouthLevel(0.12);
        void context.close();
        resolve(outcome);
      };
      const tick = () => {
        if (activeAudioRef.current !== audio) {
          finish("ended");
          return;
        }
        if (audio.paused) {
          setLiveMouthLevel(0.12);
          raf = window.requestAnimationFrame(tick);
          return;
        }
        analyser.getByteFrequencyData(samples);
        const voiceBand = samples.slice(2, 34);
        const average = voiceBand.reduce((sum, value) => sum + value, 0) / Math.max(1, voiceBand.length);
        setLiveMouthLevel(Math.min(1, 0.12 + average / 120));
        raf = window.requestAnimationFrame(tick);
      };
      audio.onplay = () => {
        if (tracking || settled) return;
        tracking = true;
        tick();
      };
      audio.onended = () => finish("ended");
      audio.onerror = () => finish("error");
      void context.resume().then(() => audio.play()).catch(() => finish("error"));
    });
  }

  function withTimeout<T>(promise: Promise<T>, timeoutMs: number) {
    return Promise.race<T | null>([
      promise,
      new Promise<null>((resolve) => window.setTimeout(() => resolve(null), timeoutMs))
    ]);
  }

  function browserSpeak(text: string) {
    setDriverPending(false);
    if (!("speechSynthesis" in window)) {
      setSpeaking(false);
      setStatusLabel(GUIDE_STATUS.online);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const voiceEffect = getVoiceEffect();
    utterance.lang = "zh-CN";
    utterance.rate = Math.max(0.65, Math.min(1.35, speechRate * voiceEffect.rate));
    utterance.volume = speechVolume;
    utterance.pitch = voiceEffect.pitch;
    const voices = window.speechSynthesis.getVoices();
    const zhVoice =
      voices.find((voice) => voice.lang.toLowerCase().startsWith("zh") && voiceEffect.voiceName.test(voice.name)) ||
      voices.find((voice) => voice.lang.toLowerCase().startsWith("zh")) ||
      voices.find((voice) => /chinese|mandarin|huihui|xiaoxiao/i.test(voice.name));
    if (zhVoice) utterance.voice = zhVoice;
    utterance.onpause = () => {
      setSpeechPaused(true);
      setStatusLabel(GUIDE_STATUS.paused);
    };
    utterance.onresume = () => {
      setSpeechPaused(false);
      setStatusLabel(GUIDE_STATUS.speaking);
    };
    utterance.onerror = () => {
      setLiveMouthLevel(0.12);
      setSpeaking(false);
      setSpeechPaused(false);
      setStatusLabel(GUIDE_STATUS.online);
    };
    let raf = 0;
    let pulse = 0;
    utterance.onstart = () => {
      setStatusLabel(GUIDE_STATUS.speaking);
      const tick = () => {
        pulse += 1;
        setLiveMouthLevel(0.28 + Math.abs(Math.sin(pulse / 2.8)) * 0.42);
        raf = window.requestAnimationFrame(tick);
      };
      tick();
    };
    utterance.onend = () => {
      window.cancelAnimationFrame(raf);
      setLiveMouthLevel(0.12);
      setSpeaking(false);
      setSpeechPaused(false);
      setStatusLabel(GUIDE_STATUS.online);
    };
    window.speechSynthesis.speak(utterance);
  }

  function getVoiceEffect() {
    if (voicePreset === "calm") {
      return { pitch: 0.88, rate: 0.92, voiceName: /yunxi|xiaoyi|kangkang|male|nan|男/i };
    }
    if (voicePreset === "bright") {
      return { pitch: 1.16, rate: 1.05, voiceName: /xiaoxiao|xiaoyi|huihui|female|nv|女/i };
    }
    if (voicePreset === "story") {
      return { pitch: 0.98, rate: 0.9, voiceName: /yunxi|xiaoyi|huihui|female|nv|女/i };
    }
    if (voicePreset === "child") {
      return { pitch: 1.22, rate: 1.08, voiceName: /xiaoxiao|huihui|female|nv|女/i };
    }
    if (voicePreset === "broadcast") {
      return { pitch: 0.94, rate: 1.02, voiceName: /yunxi|kangkang|male|nan|男/i };
    }
    return { pitch: 1.04, rate: 1, voiceName: /xiaoxiao|huihui|female|nv|女/i };
  }

  function makeLocalVisemes(text: string): VisemeFrame[] {
    return Array.from(text).filter((char) => char.trim()).slice(0, 220).map((char, index) => ({
      time: Number((index * 0.075).toFixed(2)),
      mouth: Math.min(0.96, 0.24 + (char.charCodeAt(0) % 8) / 10),
      char
    }));
  }

  function toggleListening() {
    if (listening) {
      if (pcmRecorderRef.current) {
        void stopPcmRecording();
        return;
      }
      if (mediaRecorderRef.current?.state === "recording") {
        beginVoiceBenchmarkTrace();
        mediaRecorderRef.current.stop();
        return;
      }
      const unsupportedTrace = beginVoiceBenchmarkTrace();
      failBenchmarkTrace(unsupportedTrace, E2E_BENCHMARK_FAILURE.browserRecognition);
      recognitionRef.current?.stop();
      setListening(false);
      setStatusLabel(GUIDE_STATUS.thinking);
      return;
    }
    if (typeof navigator.mediaDevices?.getUserMedia === "function") {
      void startBackendRecording();
      return;
    }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setSubtitle("当前环境暂未开放语音输入权限，可以继续使用文本提问。");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const text = event.results[0]?.[0]?.transcript || "";
      setQuestion(text);
      if (text) void submit(text);
    };
    recognition.onend = () => {
      setListening(false);
      setStatusLabel(GUIDE_STATUS.online);
    };
    recognitionRef.current = recognition;
    setListening(true);
    setStatusLabel(GUIDE_STATUS.listening);
    recognition.start();
  }

  async function startBackendRecording() {
    if (typeof navigator.mediaDevices?.getUserMedia !== "function") {
      setSubtitle("当前环境暂未开放语音输入权限，可以继续使用文本提问。");
      return;
    }
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (AudioContextCtor) {
      await startPcmRecording(AudioContextCtor);
      return;
    }
    if (!("MediaRecorder" in window)) {
      setSubtitle("当前环境暂未开放语音输入权限，可以继续使用文本提问。");
      return;
    }
    await startMediaRecorderRecording();
  }

  async function startPcmRecording(AudioContextCtor: typeof AudioContext) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContextCtor();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silence = context.createGain();
      const chunks: Float32Array[] = [];
      silence.gain.value = 0;
      processor.onaudioprocess = (event) => {
        chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(processor);
      processor.connect(silence);
      silence.connect(context.destination);
      await context.resume();
      pcmRecorderRef.current = {
        stream,
        context,
        source,
        processor,
        silence,
        chunks,
        inputSampleRate: context.sampleRate
      };
      setListening(true);
      setStatusLabel(GUIDE_STATUS.listening);
      setSubtitle("我在听，请说完后再点一次麦克风。");
    } catch {
      setSubtitle("无法开启麦克风，请允许麦克风权限，或继续使用文本提问。");
      setStatusLabel(GUIDE_STATUS.online);
    }
  }

  async function startMediaRecorderRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        void transcribeRecordedAudio(activeBenchmarkTraceRef.current);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setListening(true);
      setStatusLabel(GUIDE_STATUS.listening);
      setSubtitle("我在听，请说完后再点一次麦克风。");
    } catch {
      setSubtitle("无法开启麦克风，请允许麦克风权限，或继续使用文本提问。");
      setStatusLabel(GUIDE_STATUS.online);
    }
  }

  async function transcribeRecordedAudio(benchmarkTrace: E2EBenchmarkTrace | null) {
    const audio = new Blob(audioChunksRef.current, { type: "audio/webm" });
    await transcribeAudioBlob(audio, "question.webm", benchmarkTrace);
  }

  async function stopPcmRecording() {
    const recorder = pcmRecorderRef.current;
    if (!recorder) return;
    const benchmarkTrace = beginVoiceBenchmarkTrace();
    pcmRecorderRef.current = null;
    recorder.processor.onaudioprocess = null;
    recorder.source.disconnect();
    recorder.processor.disconnect();
    recorder.silence.disconnect();
    recorder.stream.getTracks().forEach((track) => track.stop());
    const audio = encodePcm16(recorder.chunks, recorder.inputSampleRate, 16000);
    await recorder.context.close().catch(() => undefined);
    await transcribeAudioBlob(audio, "question.pcm", benchmarkTrace);
  }

  async function transcribeAudioBlob(audio: Blob, filename: string, benchmarkTrace: E2EBenchmarkTrace | null) {
    setListening(false);
    setStatusLabel(GUIDE_STATUS.thinking);
    const formData = new FormData();
    formData.append("file", audio, filename);
    try {
      markBenchmark(benchmarkTrace, "asr_start");
      const response = await fetch(`${API_BASE}/api/asr/transcribe`, {
        method: "POST",
        body: formData
      });
      const payload = await response.json();
      markBenchmark(benchmarkTrace, "asr_done");
      setBenchmarkProviders(benchmarkTrace, { asr: String(payload?.data?.provider || "") });
      const text = String(payload?.data?.text || "").trim();
      if (!response.ok || !payload.ok) throw new Error(payload?.message || "语音识别暂不可用");
      if (!text) {
        failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.asrNoText);
        setSubtitle("这次没有听清，可以再说一遍，或直接打字问我。");
        setStatusLabel(GUIDE_STATUS.online);
        return;
      }
      setQuestion(text);
      void submit(text, benchmarkTrace);
    } catch (error) {
      failBenchmarkTrace(benchmarkTrace, E2E_BENCHMARK_FAILURE.asrFailed);
      setSubtitle(error instanceof Error ? error.message : "语音识别暂不可用，可以继续使用文本提问。");
      setStatusLabel(GUIDE_STATUS.online);
    }
  }

  function encodePcm16(chunks: Float32Array[], inputSampleRate: number, targetSampleRate: number) {
    const sampleCount = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const samples = new Float32Array(sampleCount);
    let offset = 0;
    chunks.forEach((chunk) => {
      samples.set(chunk, offset);
      offset += chunk.length;
    });
    const ratio = inputSampleRate / targetSampleRate;
    const outputLength = Math.max(1, Math.floor(samples.length / ratio));
    const output = new DataView(new ArrayBuffer(outputLength * 2));
    for (let index = 0; index < outputLength; index += 1) {
      const sourceIndex = Math.min(samples.length - 1, Math.floor(index * ratio));
      const value = Math.max(-1, Math.min(1, samples[sourceIndex] || 0));
      output.setInt16(index * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
    }
    return new Blob([output], { type: "audio/pcm" });
  }

  async function sendFeedback(logId: number, rating: number, feeling: string, text = "") {
    setFeedbackRatings((current) => ({ ...current, [logId]: rating }));
    const feedbackText = text.trim() || "仅提交星级评价";
    try {
      await apiPost("/api/feedback/text", {
        log_id: logId,
        rating,
        text: feedbackText,
        sentiment: sentimentFromRating(rating),
        topics: []
      });
    } catch {
      await apiPost("/api/feedback", { log_id: logId, rating, feeling, note: text.trim() });
    }
    setSubtitle(text.trim() ? "感谢你的建议，景区服务团队会认真查看。" : `已记录 ${rating} 星反馈。`);
  }

  function fileToBase64(file: File) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const value = String(reader.result || "");
        resolve(value.includes(",") ? value.split(",")[1] : value);
      };
      reader.onerror = () => reject(new Error("图片读取失败，请重新选择。"));
      reader.readAsDataURL(file);
    });
  }

  async function handleQuestionImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setSubtitle("请上传景点照片，再向我提问。");
      return;
    }
    try {
      const [base64, previewUrl] = await Promise.all([
        fileToBase64(file),
        Promise.resolve(URL.createObjectURL(file))
      ]);
      questionPreviewUrlsRef.current.push(previewUrl);
      setPendingImageBase64(base64);
      setPendingMediaPreview(previewUrl);
      setPendingMediaKind("image");
      setQuestion((value) => value || "这张图片里是什么景点？");
      setSubtitle("图片已加入本次提问，可以问我这是哪里、有什么故事或怎么游览。");
    } catch (error) {
      setSubtitle(error instanceof Error ? error.message : "图片读取失败，请重新选择。");
    }
  }

  function removePendingMedia() {
    setPendingImageBase64(null);
    setPendingMediaPreview(null);
    setPendingMediaKind(null);
    setSubtitle("已移除本次图片提问。");
  }

  function captureCameraFrame() {
    const video = cameraVideoElementRef.current;
    if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return null;
    const maxWidth = 900;
    const scale = Math.min(1, maxWidth / video.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const preview = canvas.toDataURL("image/jpeg", 0.84);
    return {
      base64: preview.includes(",") ? preview.split(",")[1] : preview,
      preview
    };
  }

  async function toggleCamera() {
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
      setCameraStream(null);
      setSubtitle("相机已关闭，本次提问不会附带画面。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 720 }, height: { ideal: 960 }, facingMode: "user" },
        audio: false
      });
      cameraStreamRef.current = stream;
      setCameraStream(stream);
      setSubtitle("相机已开启，提问时会截取当前画面帮助识别景点。");
    } catch {
      setSubtitle("无法开启相机，请允许相机权限，或改用上传照片。");
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  function startNewChat() {
    stopSpeechPlayback();
    setMessages([]);
    setQuestion("");
    setSubtitle("已开启新的导览对话。");
    setToolsOpen(false);
    window.localStorage.removeItem(visitorMemoryKey);
    chatWindowRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeCurrentRoute() {
    setVisibleRoutePlan(null);
    setGuideMode("conversation");
  }

  function scrollChatTop() {
    chatWindowRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <main className="tourist-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <img className="brand-icon" src="/assets/generated/app-icon-v2.png" alt="" />
          <span>灵境导游</span>
        </a>
        <nav className="visitor-nav" aria-label="主导航">
          <button className={guideMode === "conversation" ? "active" : ""} type="button" onClick={() => setGuideMode("conversation")}>智慧导览</button>
          <button className={guideMode === "itinerary" ? "active" : ""} type="button" onClick={() => activeRoutePlan ? setGuideMode("itinerary") : void submit("推荐一条适合第一次游览的路线")}>推荐游线</button>
          <a href="/admin">景区服务</a>
        </nav>
      </header>

      <section className="scenic-canvas">
        <DigitalHuman
          speaking={speaking}
          subtitle={subtitlesEnabled ? subtitle : null}
          statusLabel={presentationStatus}
          driverReady={openTalking.sessionReady || Boolean(health?.opentalking_ready)}
          voiceReady={Boolean(health?.tts_ready || health?.vivo_configured)}
          visemes={visemes}
          liveMouthLevel={liveMouthLevel}
          expression={avatarExpression}
          imageUrl={publishedProfile?.clothing_asset_url || publishedProfile?.avatar_asset_url}
          driverVideoUrl={driverVideoUrl}
          driverPending={driverPending}
          syntheticMotionEnabled={syntheticMotionEnabled}
          driverVideoRef={driverVideoRef}
          stream={openTalking.stream}
          benchmarkEnabled={benchmarkEnabled}
          mouthMotionWatchToken={mouthMotionWatchToken}
          onFirstVisibleMouth={handleFirstVisibleMouth}
        />

        <section className="guide-panel" data-mode={guideMode}>
          <div className="guide-tabs" role="tablist" aria-label="导览内容">
            <button
              className={guideMode === "conversation" ? "active" : ""}
              id="guide-tab-conversation"
              type="button"
              role="tab"
              aria-controls="guide-panel-conversation"
              aria-selected={guideMode === "conversation"}
              onClick={() => setGuideMode("conversation")}
            >
              对话
            </button>
            <button
              className={guideMode === "itinerary" ? "active" : ""}
              id="guide-tab-itinerary"
              type="button"
              role="tab"
              aria-controls="guide-panel-itinerary"
              aria-selected={guideMode === "itinerary"}
              aria-disabled={!activeRoutePlan}
              onClick={() => activeRoutePlan ? setGuideMode("itinerary") : void submit("推荐一条自然风光路线")}
            >
              当前游线{activeRoutePlan ? <span>{activeRoutePlan.steps.length}</span> : null}
            </button>
          </div>

          <div
            className={guideMode === "conversation" ? "guide-tabpanel active" : "guide-tabpanel"}
            id="guide-panel-conversation"
            role="tabpanel"
            aria-labelledby="guide-tab-conversation"
            hidden={guideMode !== "conversation"}
          >
            <div className="chat-toolbar">
              <span>{messages.length ? `${messages.length} 条对话` : "今天想从哪里开始？"}</span>
              <button type="button" onClick={startNewChat}>新话题</button>
            </div>

            <div className="chat-window" ref={chatWindowRef} role="log" aria-live="polite" aria-relevant="additions text">
              {messages.length === 0 ? (
                <div className="empty-chat">
                  <span className="welcome-mark"><Landmark size={24} /></span>
                  <h1>你好，我是{publishedGuideName}</h1>
                  <p>{publishedGuidePersona}。有问题尽管问我。</p>
                  <div className="starter-suggestions" aria-label="推荐提问">
                    {starterSuggestions.map((item) => (
                      <button key={item} type="button" onClick={() => void submit(item)}>
                        <SuggestionIcon text={item} />
                        <span>{item}</span>
                      </button>
                    ))}
                  </div>
                  {activeRoutePlan ? <ItinerarySummary plan={activeRoutePlan} onOpen={() => setGuideMode("itinerary")} /> : null}
                </div>
              ) : messages.map((message, index) => (
                <article className={`message ${message.role} ${message.routePlan ? "has-route" : ""}`} key={`${message.role}-${index}`}>
                  {message.mediaPreview ? (
                    <figure className="message-media-preview">
                      <img src={message.mediaPreview} alt={message.mediaKind === "camera" ? "本次相机画面截图" : "本次上传照片"} />
                      <figcaption>{message.mediaKind === "camera" ? "相机画面截图" : "上传照片"}</figcaption>
                    </figure>
                  ) : null}
                  {message.role === "assistant" ? (
                    <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeAssistantMarkdown(message.text)}</ReactMarkdown></div>
                  ) : <p>{message.text}</p>}
                  {message.routePlan?.steps?.length ? <ItinerarySummary plan={message.routePlan} onOpen={() => setGuideMode("itinerary")} /> : null}
                  {message.role === "assistant" && index === latestAssistantIndex && followUpSuggestions.length ? (
                    <FollowUpSuggestions suggestions={followUpSuggestions} onChoose={(item) => void submit(item)} />
                  ) : null}
                  {message.logId ? (
                    <StarFeedback
                      rating={feedbackRatings[message.logId] || 0}
                      onChoose={(rating) => void sendFeedback(message.logId!, rating, feelingFromRating(rating))}
                      onSubmit={(rating, note) => void sendFeedback(message.logId!, rating, feelingFromRating(rating), note)}
                    />
                  ) : null}
                </article>
              ))}
              {loading ? (
                <article className="message assistant loading-message">
                  <div className="typing-dots" aria-label="正在整理回答"><span /><span /><span /></div>
                  <p>正在查找景区资料…</p>
                </article>
              ) : null}
            </div>

            {(speaking || speechPaused) ? (
              <div className="playback-strip">
                <span>{presentationStatus}</span>
                <button type="button" onClick={toggleSpeechPlayback}>{speechPaused ? <Play size={16} /> : <Pause size={16} />}{speechPaused ? "继续" : "暂停"}</button>
                <button type="button" onClick={() => stopSpeechPlayback()}><Square size={16} />停止</button>
              </div>
            ) : null}

            {toolsOpen ? (
              <div className="composer-tools-panel">
                <div className="tool-card-row">
                  <label className="tool-card"><ImagePlus size={18} /><span>上传照片</span><input type="file" accept="image/*" onChange={handleQuestionImage} /></label>
                  <button className={cameraStream ? "tool-card active" : "tool-card"} type="button" onClick={() => void toggleCamera()}>{cameraStream ? <CameraOff size={18} /> : <Camera size={18} />}<span>{cameraStream ? "关闭相机" : "相机识景"}</span></button>
                  <button className={subtitlesEnabled ? "tool-card active" : "tool-card"} type="button" onClick={() => setSubtitlesEnabled((value) => !value)}><SlidersHorizontal size={18} /><span>字幕{subtitlesEnabled ? "开" : "关"}</span></button>
                </div>
                <div className="experience-controls compact-controls" aria-label="讲解体验设置">
                  <label>音色<select value={voicePreset} onChange={(event) => setVoicePreset(event.target.value)}><option value="published">当前发布声音</option><option value="gentle">清甜导游</option><option value="calm">沉稳讲解</option><option value="bright">亲子陪伴</option><option value="story">故事讲述</option><option value="child">轻快互动</option><option value="broadcast">现场播报</option></select></label>
                  <label>风格<select value={guideStyle} onChange={(event) => setGuideStyle(event.target.value)}><option value="自然讲解">自然讲解</option><option value="文化深度">文化深度</option><option value="简洁提示">简洁提示</option><option value="亲子陪伴">亲子陪伴</option><option value="拍照推荐">拍照推荐</option></select></label>
                  <label>语速 <b>{speechRate.toFixed(2)}×</b><input aria-label="讲解语速" type="range" min="0.7" max="1.3" step="0.05" value={speechRate} onChange={(event) => setSpeechRate(Number(event.target.value))} /></label>
                  <label>音量 <b>{Math.round(speechVolume * 100)}%</b><input aria-label="讲解音量" type="range" min="0" max="1" step="0.05" value={speechVolume} onChange={(event) => setSpeechVolume(Number(event.target.value))} /></label>
                </div>
              </div>
            ) : null}

            <form className={question.trim() ? "ask-form composer-form is-typing" : "ask-form composer-form is-idle"} onSubmit={handleSubmit}>
              <button className={listening ? "icon-button active" : "icon-button"} type="button" onClick={toggleListening} aria-label={listening ? "停止录音" : "语音提问"}>{listening ? <Square size={19} /> : <Mic size={19} />}</button>
              <input aria-label="向数字人提问" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="问景点、演出或游线…" />
              {question.trim() ? (
                <button className="composer-send-button" type="submit" disabled={loading} aria-label="发送问题">{loading ? <Volume2 size={18} /> : <Send size={18} />}</button>
              ) : (
                <button className={toolsOpen ? "icon-button active" : "icon-button"} type="button" onClick={() => setToolsOpen((value) => !value)} aria-label={toolsOpen ? "收起更多功能" : "打开更多功能"}>{toolsOpen ? <X size={19} /> : <Plus size={19} />}</button>
              )}
            </form>
            {pendingMediaPreview ? (
              <div className="pending-media-pill"><img src={pendingMediaPreview} alt="待提问照片预览" /><span>照片已加入本次提问</span><button type="button" onClick={removePendingMedia}>移除</button></div>
            ) : cameraStream ? (
              <div className="pending-media-pill camera-preview"><video ref={cameraVideoElementRef} muted playsInline aria-label="相机取景画面" /><span>提问时截取当前画面</span></div>
            ) : null}
          </div>

          <div
            className={guideMode === "itinerary" ? "guide-tabpanel active" : "guide-tabpanel"}
            id="guide-panel-itinerary"
            role="tabpanel"
            aria-labelledby="guide-tab-itinerary"
            hidden={guideMode !== "itinerary"}
          >
            {activeRoutePlan ? (
              <ItineraryPanel
                plan={activeRoutePlan}
                onCloseRoute={closeCurrentRoute}
                onNarrateStop={(step) => {
                  setGuideMode("conversation");
                  void submit(`${step.name}有什么亮点？`);
                }}
                onReplace={(interest) => void submit(interest)}
              />
            ) : (
              <div className="empty-itinerary"><MapPinned size={30} /><h2>还没有当前游线</h2><p>告诉我同行的人和偏好，我来安排。</p><button type="button" onClick={() => void submit("推荐一条适合第一次游览的路线")}>生成推荐游线</button></div>
            )}
          </div>
        </section>
      </section>
      {showScrollTop ? (
        <button className="floating-rocket is-visible" type="button" onClick={scrollChatTop} aria-label="回到顶部" data-tip="回到顶部">
          <Rocket size={20} />
        </button>
      ) : null}
    </main>
  );
}

function StarFeedback({
  rating,
  onChoose,
  onSubmit
}: {
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
            <button
              aria-checked={selectedRating === value}
              aria-label={`${value} 星`}
              className={value <= selectedRating ? "active" : ""}
              key={value}
              onClick={() => {
                setDraftRating(value);
                onChoose(value);
              }}
              role="radio"
              type="button"
            >
              <Star size={17} fill="currentColor" />
            </button>
          ))}
        </div>
      </div>
      {selectedRating ? (
        <button className="feedback-note-toggle" type="button" onClick={() => setShowNote((value) => !value)}>
          {showNote ? "收起建议" : "补充建议"}
        </button>
      ) : null}
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

function FollowUpSuggestions({ suggestions, onChoose }: { suggestions: string[]; onChoose: (question: string) => void }) {
  return (
    <div className="follow-up-suggestions" aria-label="根据这次对话推荐的问题">
      <span>接着可以问</span>
      <div>
        {suggestions.map((item) => (
          <button key={item} type="button" onClick={() => onChoose(item)}>
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}

function feelingFromRating(rating: number) {
  if (rating >= 5) return "满意";
  if (rating === 4) return "有帮助";
  if (rating === 3) return "一般";
  return "待改进";
}

function sentimentFromRating(rating: number): "positive" | "neutral" | "negative" {
  if (rating >= 4) return "positive";
  if (rating === 3) return "neutral";
  return "negative";
}

function buildStarterSuggestions(faqs: string[]) {
  return uniqueQuestions([
    ...faqs,
    "九龙灌浴今天怎么看？",
    "帮我规划一条少走路路线",
    "带孩子先去哪里？"
  ]).slice(0, 3);
}

function buildFollowUpSuggestions(messages: Message[], faqs: string[], routePlan: RoutePlan | null) {
  const lastUser = [...messages].reverse().find((message) => message.role === "user")?.text || "";
  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant")?.text || "";
  const recent = `${lastUser}\n${lastAssistant}`;
  const routeStep = routePlan?.steps?.[0]?.name;
  const candidates: string[] = [];
  if (/路线|规划|怎么走|行程|半日|一日/.test(recent)) {
    candidates.push(
      routeStep ? `${routeStep}这一站有什么亮点？` : "这条路线每一站怎么安排时间？",
      "如果少走路，路线怎么调整？",
      "附近适合拍照的位置有哪些？"
    );
  }
  if (/九龙|灌浴|表演|演出/.test(recent)) {
    candidates.push("九龙灌浴适合提前多久到？", "看完表演下一站去哪？", "这个表演有什么文化寓意？");
  }
  if (/亲子|孩子|家庭|小朋友/.test(recent)) {
    candidates.push("亲子游需要避开什么拥挤时段？", "孩子最容易感兴趣的点是哪几个？", "有没有轻松一点的亲子路线？");
  }
  if (/历史|文化|佛教|建筑|故事/.test(recent)) {
    candidates.push("这里背后的历史故事是什么？", "哪些景点最能体现文化特色？", "适合深度讲解的路线怎么走？");
  }
  if (/拍照|照片|图片|识别/.test(recent)) {
    candidates.push("这个位置怎么拍更好看？", "附近还有哪些出片点？", "这张图里的景点有什么故事？");
  }
  candidates.push(...faqs, "现在附近先看哪个景点？", "帮我换成更轻松的讲解方式");
  return uniqueQuestions(candidates).filter((item) => item !== lastUser).slice(0, 3);
}

function uniqueQuestions(items: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  items.forEach((item) => {
    const value = item.trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    result.push(value);
  });
  return result;
}
