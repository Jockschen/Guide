"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

type SessionStatus = "idle" | "connecting" | "ready" | "streaming" | "fallback";

type SessionResponse = {
  session_id: string;
  status?: string;
};

type SessionEnvelope<T> = T | { ok: boolean; data: T; message?: string };

export type AudioUploadObserver = {
  onUploadStart?(at: number): void;
  onUploadAck?(at: number): void;
  onFailure?(reason: string): void;
};

function unwrap<T>(payload: SessionEnvelope<T>): T {
  if (payload && typeof payload === "object" && "data" in payload) return payload.data;
  return payload as T;
}

async function waitForIce(peer: RTCPeerConnection, timeoutMs = 1800) {
  if (peer.iceGatheringState === "complete") return;
  await new Promise<void>((resolve) => {
    const timer = window.setTimeout(done, timeoutMs);
    function done() {
      window.clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", onChange);
      resolve();
    }
    function onChange() {
      if (peer.iceGatheringState === "complete") done();
    }
    peer.addEventListener("icegatheringstatechange", onChange);
  });
}

async function waitForSessionReady(sessionId: string, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${API_BASE}/api/avatar/sessions/${encodeURIComponent(sessionId)}`, {
        cache: "no-store"
      });
      if (response.ok) {
        const state = unwrap(await response.json() as SessionEnvelope<{ state?: string; status?: string }>);
        const value = String(state.state || state.status || "").toLowerCase();
        // OpenTalking writes `created` before the QuickTalk runner has loaded.
        // Offering WebRTC at that point races the worker and yields no video track.
        if (["worker_ready", "ready", "speaking"].includes(value)) return true;
        if (["failed", "closed", "error"].includes(value)) return false;
      }
    } catch {
      // The official worker can briefly restart its session view while the avatar is loading.
    }
    await new Promise((resolve) => window.setTimeout(resolve, 300));
  }
  return false;
}

export function useOpenTalkingSession() {
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const connectionRef = useRef<Promise<boolean> | null>(null);
  const mountedRef = useRef(true);

  const destroyLocalResources = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    const peer = peerRef.current;
    peerRef.current = null;
    peer?.getReceivers().forEach((receiver) => receiver.track?.stop());
    peer?.getSenders().forEach((sender) => sender.track?.stop());
    peer?.close();
    setStream((current) => {
      current?.getTracks().forEach((track) => track.stop());
      return null;
    });
  }, []);

  const close = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    sessionIdRef.current = null;
    connectionRef.current = null;
    destroyLocalResources();
    if (mountedRef.current) setStatus("idle");
    if (!sessionId) return;
    await fetch(`${API_BASE}/api/avatar/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      keepalive: true
    }).catch(() => undefined);
  }, [destroyLocalResources]);

  const connect = useCallback(async () => {
    if (sessionIdRef.current && peerRef.current) return true;
    if (connectionRef.current) return connectionRef.current;
    if (typeof window === "undefined" || !("RTCPeerConnection" in window)) {
      setStatus("fallback");
      return false;
    }

    const pending = (async () => {
      setStatus("connecting");
      try {
        const sessionRequest = await fetch(`${API_BASE}/api/avatar/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const sessionPayload = unwrap(await sessionRequest.json() as SessionEnvelope<SessionResponse>);
        if (!sessionRequest.ok || !sessionPayload?.session_id) throw new Error("session unavailable");
        const sessionId = sessionPayload.session_id;
        sessionIdRef.current = sessionId;
        if (!(await waitForSessionReady(sessionId))) throw new Error("session initialization timed out");

        const peer = new RTCPeerConnection();
        peerRef.current = peer;
        peer.addTransceiver("video", { direction: "recvonly" });
        peer.addTransceiver("audio", { direction: "recvonly" });
        peer.ontrack = (event) => {
          if (!mountedRef.current) return;
          setStream((current) => {
            const next = event.streams[0] || current || new MediaStream();
            if (!next.getTracks().some((track) => track.id === event.track.id)) next.addTrack(event.track);
            return next;
          });
          setStatus("streaming");
        };
        peer.onconnectionstatechange = () => {
          if (!mountedRef.current) return;
          if (peer.connectionState === "connected") setStatus((current) => current === "streaming" ? current : "ready");
          if (["failed", "closed", "disconnected"].includes(peer.connectionState)) setStatus("fallback");
        };

        const offer = await peer.createOffer();
        await peer.setLocalDescription(offer);
        await waitForIce(peer);
        const offerResponse = await fetch(`${API_BASE}/api/avatar/sessions/${encodeURIComponent(sessionId)}/webrtc/offer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sdp: peer.localDescription?.sdp || offer.sdp,
            type: peer.localDescription?.type || offer.type
          })
        });
        const answer = unwrap(await offerResponse.json() as SessionEnvelope<RTCSessionDescriptionInit>);
        if (!offerResponse.ok || !answer?.sdp || !answer?.type) throw new Error("offer unavailable");
        await peer.setRemoteDescription(answer);

        const eventsUrl = `${API_BASE}/api/avatar/sessions/${encodeURIComponent(sessionId)}/events`;
        const events = new EventSource(eventsUrl);
        eventSourceRef.current = events;
        events.onopen = () => mountedRef.current && setStatus((current) => current === "streaming" ? current : "ready");
        events.onerror = () => {
          // Event delivery may reconnect independently; media and TTS fallbacks remain usable.
        };
        if (mountedRef.current) setStatus((current) => current === "streaming" ? current : "ready");
        return true;
      } catch {
        destroyLocalResources();
        sessionIdRef.current = null;
        if (mountedRef.current) setStatus("fallback");
        return false;
      } finally {
        connectionRef.current = null;
      }
    })();
    connectionRef.current = pending;
    return pending;
  }, [destroyLocalResources]);

  const interrupt = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;
    await fetch(`${API_BASE}/api/avatar/sessions/${encodeURIComponent(sessionId)}/interrupt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    }).catch(() => undefined);
  }, []);

  const enqueueAudio = useCallback(async (audioUrl: string, observer?: AudioUploadObserver) => {
    const connected = await connect();
    const sessionId = sessionIdRef.current;
    if (!connected || !sessionId) {
      observer?.onFailure?.("OpenTalking session 未连接");
      return false;
    }
    try {
      const audioResponse = await fetch(audioUrl);
      if (!audioResponse.ok) {
        observer?.onFailure?.("真实 TTS 音频无法读取");
        return false;
      }
      const audio = await audioResponse.blob();
      const formData = new FormData();
      formData.append("file", audio, "narration.wav");
      observer?.onUploadStart?.(performance.now());
      const response = await fetch(`${API_BASE}/api/avatar/sessions/${encodeURIComponent(sessionId)}/audio`, {
        method: "POST",
        body: formData
      });
      observer?.onUploadAck?.(performance.now());
      if (!response.ok) observer?.onFailure?.("OpenTalking 音频入队失败");
      return response.ok;
    } catch {
      observer?.onFailure?.("OpenTalking 音频上传异常");
      return false;
    }
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    void connect();
    return () => {
      mountedRef.current = false;
      void close();
    };
  }, [close, connect]);

  return {
    status,
    stream,
    connect,
    enqueueAudio,
    interrupt,
    close,
    sessionReady: status === "ready" || status === "streaming",
    streamReady: status === "streaming" && Boolean(stream)
  };
}
