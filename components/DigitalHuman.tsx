"use client";

import { RefObject, useEffect, useRef, useState } from "react";

export type GuideStatus = "导游在线" | "正在聆听" | "正在整理" | "正在讲解" | "讲解已暂停";

export type VisemeFrame = {
  time: number;
  mouth: number;
  char?: string;
};

export function DigitalHuman({
  speaking,
  subtitle,
  statusLabel,
  driverReady,
  voiceReady,
  expression = "friendly",
  imageUrl,
  driverVideoUrl,
  driverPending = false,
  driverVideoRef,
  stream,
  benchmarkEnabled = false,
  mouthMotionWatchToken,
  onFirstVisibleMouth
}: {
  speaking: boolean;
  subtitle: string | null;
  statusLabel: GuideStatus;
  driverReady: boolean;
  voiceReady: boolean;
  visemes?: VisemeFrame[];
  liveMouthLevel?: number;
  expression?: "friendly" | "listening" | "thinking" | "speaking";
  imageUrl?: string | null;
  driverVideoUrl?: string | null;
  driverPending?: boolean;
  syntheticMotionEnabled?: boolean;
  driverVideoRef?: RefObject<HTMLVideoElement | null>;
  stream?: MediaStream | null;
  benchmarkEnabled?: boolean;
  mouthMotionWatchToken?: string | null;
  onFirstVisibleMouth?: (at: number) => void;
}) {
  const streamVideoRef = useRef<HTMLVideoElement | null>(null);
  const idleMouthDeltasRef = useRef<number[]>([]);
  const previousMouthFrameRef = useRef<Uint8ClampedArray | null>(null);
  const detectedWatchTokenRef = useRef<string | null>(null);
  const [streamVisible, setStreamVisible] = useState(false);
  const [driverVideoReady, setDriverVideoReady] = useState(false);
  const statusReady = driverReady || voiceReady;

  useEffect(() => {
    const video = streamVideoRef.current;
    if (!video) return;
    video.srcObject = stream ?? null;
    setStreamVisible(false);
    if (stream) {
      video.playsInline = true;
      video.autoplay = true;
      void video.play().catch(() => undefined);
    }
  }, [stream]);

  useEffect(() => {
    idleMouthDeltasRef.current = [];
    previousMouthFrameRef.current = null;
    detectedWatchTokenRef.current = null;
  }, [stream]);

  useEffect(() => {
    if (!benchmarkEnabled || !stream) return;
    const video = streamVideoRef.current as (HTMLVideoElement & {
      requestVideoFrameCallback?: (callback: () => void) => number;
      cancelVideoFrameCallback?: (handle: number) => void;
    }) | null;
    if (!video?.requestVideoFrameCallback) return;
    const canvas = document.createElement("canvas");
    canvas.width = 72;
    canvas.height = 54;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return;
    let cancelled = false;
    let frameHandle = 0;

    const sampleFrame = () => {
      if (cancelled) return;
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        const sourceX = video.videoWidth * 0.41;
        const sourceY = video.videoHeight * 0.42;
        const sourceWidth = video.videoWidth * 0.18;
        const sourceHeight = video.videoHeight * 0.15;
        context.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
        const current = context.getImageData(0, 0, canvas.width, canvas.height).data;
        const previous = previousMouthFrameRef.current;
        if (previous && previous.length === current.length) {
          let sum = 0;
          for (let index = 0; index < current.length; index += 4) {
            sum += Math.abs(current[index] - previous[index]);
            sum += Math.abs(current[index + 1] - previous[index + 1]);
            sum += Math.abs(current[index + 2] - previous[index + 2]);
          }
          const delta = sum / Math.max(1, current.length * 0.75);
          if (!mouthMotionWatchToken) {
            const idle = idleMouthDeltasRef.current;
            idle.push(delta);
            if (idle.length > 60) idle.shift();
          } else if (detectedWatchTokenRef.current !== mouthMotionWatchToken) {
            const orderedIdle = [...idleMouthDeltasRef.current].sort((a, b) => a - b);
            const p95Index = Math.max(0, Math.ceil(orderedIdle.length * 0.95) - 1);
            const idleP95 = orderedIdle[p95Index] || 0;
            const threshold = Math.max(1, idleP95 * 1.5);
            if (orderedIdle.length >= 5 && delta >= threshold) {
              detectedWatchTokenRef.current = mouthMotionWatchToken;
              onFirstVisibleMouth?.(performance.now());
            }
          }
        }
        previousMouthFrameRef.current = new Uint8ClampedArray(current);
      }
      frameHandle = video.requestVideoFrameCallback!(sampleFrame);
    };
    frameHandle = video.requestVideoFrameCallback(sampleFrame);
    return () => {
      cancelled = true;
      if (frameHandle) video.cancelVideoFrameCallback?.(frameHandle);
    };
  }, [benchmarkEnabled, mouthMotionWatchToken, onFirstVisibleMouth, stream]);

  useEffect(() => {
    setDriverVideoReady(false);
    const video = driverVideoRef?.current;
    if (!driverVideoUrl || !video) return;
    video.currentTime = 0;
    video.load();
  }, [driverVideoRef, driverVideoUrl]);

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
}
