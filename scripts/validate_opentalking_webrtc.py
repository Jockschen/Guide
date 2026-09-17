from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import wave

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIO_DIR = ROOT / "backend" / "storage" / "audio"
DEFAULT_REPORT = ROOT / "reports" / "quality" / "opentalking-webrtc-latest.json"


def _select_audio_path(requested: str | Path | None, audio_dir: Path = DEFAULT_AUDIO_DIR) -> Path:
    if requested:
        selected = Path(requested)
        if not selected.is_absolute():
            selected = (ROOT / selected).resolve()
        if not selected.is_file() or selected.stat().st_size <= 44:
            raise FileNotFoundError(f"A valid PCM WAV was not found at {selected}")
        return selected

    candidates = [
        path
        for path in audio_dir.glob("*.wav")
        if path.is_file() and path.stat().st_size > 44
    ]
    if not candidates:
        raise FileNotFoundError(f"No non-empty WAV file was found in {audio_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _audio_metadata(audio_path: Path, *, provider: str = "") -> dict[str, Any]:
    provider_name = provider.strip().lower()
    if not provider_name:
        stem = audio_path.stem.lower()
        provider_name = next(
            (
                candidate
                for candidate in ("edge", "vivo", "sherpa-onnx", "sapi", "mock")
                if stem == candidate or stem.startswith(f"{candidate}-")
            ),
            "unknown",
        )
    with wave.open(str(audio_path), "rb") as source:
        sample_rate = int(source.getframerate())
        frame_count = int(source.getnframes())
        channels = int(source.getnchannels())
        sample_width = int(source.getsampwidth())
    return {
        "source_file": str(audio_path),
        "provider": provider_name,
        "format": "pcm_wav",
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "sample_width_bits": sample_width * 8,
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0.0,
        "size_bytes": audio_path.stat().st_size,
    }


def _observed_fps(frame_times: Sequence[float]) -> float:
    if len(frame_times) < 2 or frame_times[-1] <= frame_times[0]:
        return 0.0
    return round((len(frame_times) - 1) / (frame_times[-1] - frame_times[0]), 2)


def _mouth_crop(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    return frame[
        int(height * 0.42) : max(int(height * 0.57), int(height * 0.42) + 1),
        int(width * 0.41) : max(int(width * 0.59), int(width * 0.41) + 1),
    ]


def _delta_series(frames: Sequence[np.ndarray]) -> list[float]:
    values: list[float] = []
    for before, after in zip(frames, frames[1:]):
        a = _mouth_crop(before).astype(np.float32)
        b = _mouth_crop(after).astype(np.float32)
        values.append(float(np.mean(np.abs(b - a))))
    return values


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float32), percentile))


def _unique_frame_count(frames: Sequence[np.ndarray]) -> int:
    # Downsampling keeps the proof inexpensive while still detecting repeated idle frames.
    return len({hash(frame[::8, ::8].tobytes()) for frame in frames})


def _frame_motion_metrics(
    idle_frames: Sequence[np.ndarray],
    speaking_frames: Sequence[np.ndarray],
) -> dict[str, int | float]:
    idle_deltas = _delta_series(idle_frames)
    speaking_deltas = _delta_series(speaking_frames)
    return {
        "idle_frame_count": len(idle_frames),
        "speaking_frame_count": len(speaking_frames),
        "speaking_unique_frames": _unique_frame_count(speaking_frames),
        "idle_mouth_delta_mean": round(float(np.mean(idle_deltas)), 4) if idle_deltas else 0.0,
        "idle_mouth_delta_p95": round(_percentile(idle_deltas, 95), 4),
        "speaking_mouth_delta_mean": round(float(np.mean(speaking_deltas)), 4) if speaking_deltas else 0.0,
        "speaking_mouth_delta_p95": round(_percentile(speaking_deltas, 95), 4),
        "speaking_mouth_delta_max": round(max(speaking_deltas, default=0.0), 4),
    }


def _motion_passes(
    metrics: dict[str, int | float],
    *,
    video_track_received: bool,
    peer_connected: bool,
    speaking_state_seen: bool,
) -> tuple[bool, dict[str, bool]]:
    idle_p95 = float(metrics.get("idle_mouth_delta_p95", 0.0))
    mouth_peak = float(metrics.get("speaking_mouth_delta_max", 0.0))
    checks = {
        "video_track_received": video_track_received,
        "peer_connected": peer_connected,
        "speaking_state_seen": speaking_state_seen,
        "enough_streamed_frames": int(metrics.get("speaking_frame_count", 0)) >= 40,
        "frames_are_not_frozen": int(metrics.get("speaking_unique_frames", 0)) >= 10,
        "visible_mouth_motion": mouth_peak >= max(1.0, idle_p95 * 1.5),
    }
    return all(checks.values()), checks


def _motion_pair(frames: Sequence[np.ndarray]) -> tuple[np.ndarray, np.ndarray, int, float] | None:
    deltas = _delta_series(frames)
    if not deltas:
        return None
    index = max(range(len(deltas)), key=deltas.__getitem__)
    return frames[index], frames[index + 1], index + 1, deltas[index]


async def _wait_for_ice(peer: Any, timeout: float = 5.0) -> None:
    if peer.iceGatheringState == "complete":
        return
    event = asyncio.Event()

    @peer.on("icegatheringstatechange")
    async def ice_state_changed() -> None:
        if peer.iceGatheringState == "complete":
            event.set()

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        # Host candidates gathered before the timeout are enough for same-machine validation.
        pass


async def _wait_for_frames(
    frames: list[np.ndarray],
    target: int,
    *,
    timeout: float,
) -> None:
    deadline = time.perf_counter() + timeout
    while len(frames) < target:
        if time.perf_counter() >= deadline:
            return
        await asyncio.sleep(0.04)


def _unwrap(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("The service returned a non-object response")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise RuntimeError("The service response did not contain an object payload")
    return data


async def validate_live_chain(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import httpx
        from aiortc import RTCPeerConnection, RTCSessionDescription
    except ImportError as exc:
        raise RuntimeError(
            "Run this script with third_party/opentalking/.venv/Scripts/python.exe "
            "so aiortc, httpx, PyAV, and NumPy are available."
        ) from exc

    audio_path = _select_audio_path(args.audio, Path(args.audio_dir))
    audio_metadata = _audio_metadata(audio_path, provider=str(args.audio_provider or ""))
    base_url = str(args.base_url).rstrip("/")
    peer = RTCPeerConnection()
    peer.addTransceiver("video", direction="recvonly")
    peer.addTransceiver("audio", direction="recvonly")
    session_id: str | None = None
    frames: list[np.ndarray] = []
    frame_times: list[float] = []
    frame_media_times: list[float] = []
    track_kinds: set[str] = set()
    consumers: list[asyncio.Task[Any]] = []
    video_track_ready = asyncio.Event()
    started = time.perf_counter()

    @peer.on("track")
    def on_track(track: Any) -> None:
        track_kinds.add(str(track.kind))
        if track.kind == "video":
            video_track_ready.set()

        async def consume() -> None:
            try:
                while True:
                    frame = await track.recv()
                    if track.kind == "video":
                        frames.append(frame.to_ndarray(format="rgb24"))
                        frame_times.append(time.perf_counter())
                        frame_media_times.append(
                            float(frame.pts * frame.time_base)
                            if frame.pts is not None and frame.time_base is not None
                            else 0.0
                        )
            except Exception:
                return

        consumers.append(asyncio.create_task(consume()))

    result: dict[str, Any] = {
        "ok": False,
        "transport": "webrtc",
        "model": "quicktalk",
        "base_url": base_url,
        "audio": audio_metadata,
    }
    timeout = httpx.Timeout(max(float(args.session_timeout), 30.0), connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            create_started = time.perf_counter()
            response = await client.post(
                f"{base_url}/api/avatar/sessions",
                json={"client_id": "opentalking-webrtc-proof"},
            )
            response.raise_for_status()
            session = _unwrap(response.json())
            session_id = str(session.get("session_id") or "")
            if not session_id:
                raise RuntimeError("Session creation returned no session_id")
            avatar_id = str(session.get("avatar_id") or "")
            model = str(session.get("model") or "quicktalk")
            result.update(
                {
                    "avatar_id": avatar_id,
                    "model": model,
                    "profile": {
                        "avatar_id": avatar_id,
                        "model": model,
                        "target_fps": int(args.target_fps),
                        "target_resolution": str(args.target_resolution),
                    },
                }
            )

            ready_deadline = time.perf_counter() + float(args.session_timeout)
            session_state = str(session.get("status") or "")
            while time.perf_counter() < ready_deadline:
                state_response = await client.get(f"{base_url}/api/avatar/sessions/{session_id}")
                state_response.raise_for_status()
                state = _unwrap(state_response.json())
                session_state = str(state.get("state") or state.get("status") or session_state).lower()
                if session_state in {"worker_ready", "ready", "speaking"}:
                    break
                if session_state in {"error", "failed", "closed"}:
                    raise RuntimeError(f"Session entered terminal state: {session_state}")
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError(f"Session did not become ready; last state: {session_state}")
            ready_at = time.perf_counter()

            offer = await peer.createOffer()
            await peer.setLocalDescription(offer)
            await _wait_for_ice(peer)
            offer_started = time.perf_counter()
            offer_response = await client.post(
                f"{base_url}/api/avatar/sessions/{session_id}/webrtc/offer",
                json={
                    "sdp": peer.localDescription.sdp,
                    "type": peer.localDescription.type,
                },
            )
            offer_response.raise_for_status()
            answer = _unwrap(offer_response.json())
            await peer.setRemoteDescription(
                RTCSessionDescription(str(answer["sdp"]), str(answer["type"]))
            )
            offer_finished = time.perf_counter()

            await asyncio.wait_for(video_track_ready.wait(), timeout=float(args.capture_timeout))
            await _wait_for_frames(
                frames,
                int(args.idle_frames),
                timeout=float(args.capture_timeout),
            )
            if len(frames) < int(args.idle_frames):
                raise TimeoutError(f"Only {len(frames)} idle video frames arrived")
            idle_count = len(frames)
            upload_started = time.perf_counter()
            with audio_path.open("rb") as audio_file:
                upload_response = await client.post(
                    f"{base_url}/api/avatar/sessions/{session_id}/audio",
                    files={"file": ("narration.wav", audio_file, "audio/wav")},
                )
            upload_response.raise_for_status()
            upload_finished = time.perf_counter()

            speaking_seen_at: float | None = None
            capture_deadline = time.perf_counter() + float(args.capture_timeout)
            target = idle_count + int(args.speaking_frames)
            last_state = session_state
            while time.perf_counter() < capture_deadline and len(frames) < target:
                state_response = await client.get(f"{base_url}/api/avatar/sessions/{session_id}")
                state_response.raise_for_status()
                state = _unwrap(state_response.json())
                last_state = str(state.get("state") or state.get("status") or last_state).lower()
                if last_state == "speaking" and speaking_seen_at is None:
                    speaking_seen_at = time.perf_counter()
                await asyncio.sleep(0.08)

            idle_frames = frames[max(0, idle_count - int(args.idle_frames)) : idle_count]
            speaking_frames = frames[idle_count:]
            speaking_times = frame_times[idle_count:]
            speaking_media_times = frame_media_times[idle_count:]
            metrics = _frame_motion_metrics(idle_frames, speaking_frames)
            passed, checks = _motion_passes(
                metrics,
                video_track_received="video" in track_kinds,
                peer_connected=peer.connectionState == "connected",
                speaking_state_seen=speaking_seen_at is not None,
            )

            idle_p95 = float(metrics["idle_mouth_delta_p95"])
            motion_threshold = max(1.0, idle_p95 * 1.5)
            motion_at: float | None = None
            for index, delta in enumerate(_delta_series(speaking_frames), start=1):
                if delta >= motion_threshold and index < len(speaking_times):
                    motion_at = speaking_times[index]
                    break

            validator_decode_fps = _observed_fps(speaking_times)
            media_timeline_fps = _observed_fps(speaking_media_times)
            stream_height = int(speaking_frames[0].shape[0]) if speaking_frames else 0
            stream_width = int(speaking_frames[0].shape[1]) if speaking_frames else 0
            result.update(
                {
                    "ok": passed,
                    "session_id": session_id,
                    "session_state_after_capture": last_state,
                    "track_kinds": sorted(track_kinds),
                    "peer_connection_state": peer.connectionState,
                    "checks": checks,
                    "metrics": metrics,
                    "latency_ms": {
                        "session_create_to_ready": round((ready_at - create_started) * 1000, 1),
                        "webrtc_offer": round((offer_finished - offer_started) * 1000, 1),
                        "session_create_to_first_video_frame": round(
                            ((frame_times[0] if frame_times else offer_finished) - create_started) * 1000,
                            1,
                        ),
                        "audio_upload": round((upload_finished - upload_started) * 1000, 1),
                        "audio_to_speaking_state": (
                            round((speaking_seen_at - upload_started) * 1000, 1)
                            if speaking_seen_at is not None
                            else None
                        ),
                        "audio_to_visible_mouth_motion": (
                            round((motion_at - upload_started) * 1000, 1)
                            if motion_at is not None
                            else None
                        ),
                    },
                    "stream": {
                        "width": stream_width,
                        "height": stream_height,
                        "resolution": f"{stream_width}x{stream_height}" if stream_width and stream_height else "",
                        "target_fps": int(args.target_fps),
                        "media_timeline_fps": media_timeline_fps,
                        "validator_decode_fps": validator_decode_fps,
                        "captured_seconds": round(
                            (speaking_times[-1] - speaking_times[0]) if len(speaking_times) > 1 else 0.0,
                            3,
                        ),
                        "media_timeline_seconds": round(
                            (
                                speaking_media_times[-1] - speaking_media_times[0]
                                if len(speaking_media_times) > 1
                                else 0.0
                            ),
                            3,
                        ),
                    },
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            )

            evidence_pair = _motion_pair(speaking_frames)
            if evidence_pair is not None:
                try:
                    from PIL import Image

                    before, after, frame_index, peak = evidence_pair
                    evidence_dir = Path(args.output).resolve().parent / "opentalking-webrtc-evidence"
                    evidence_dir.mkdir(parents=True, exist_ok=True)
                    before_path = evidence_dir / "mouth-before.png"
                    after_path = evidence_dir / "mouth-motion-peak.png"
                    Image.fromarray(before).save(before_path)
                    Image.fromarray(after).save(after_path)
                    result["evidence"] = {
                        "before_frame": str(before_path),
                        "motion_frame": str(after_path),
                        "motion_frame_index": frame_index,
                        "mouth_delta": round(float(peak), 4),
                    }
                except (ImportError, OSError, ValueError):
                    result["evidence"] = {"warning": "Frame evidence could not be written"}

            if session_id:
                await client.delete(f"{base_url}/api/avatar/sessions/{session_id}")
                session_id = None
    finally:
        if session_id:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as cleanup_client:
                    await cleanup_client.delete(f"{base_url}/api/avatar/sessions/{session_id}")
            except Exception:
                pass
        await peer.close()
        for task in consumers:
            task.cancel()

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the live OpenTalking QuickTalk session + WebRTC + uploaded-audio chain.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LINGJING_API_BASE_URL", "http://127.0.0.1:8000"),
        help="Lingjing backend URL; the validator intentionally exercises the same proxy used by the browser.",
    )
    parser.add_argument("--audio", default=None, help="PCM WAV to upload; latest valid WAV is used by default.")
    parser.add_argument("--audio-dir", default=str(DEFAULT_AUDIO_DIR))
    parser.add_argument("--audio-provider", default="", help="Optional source label; inferred from filename by default.")
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--target-fps", type=int, default=25)
    parser.add_argument("--target-resolution", default="720x720")
    parser.add_argument("--idle-frames", type=int, default=30)
    parser.add_argument("--speaking-frames", type=int, default=125)
    parser.add_argument("--session-timeout", type=float, default=90.0)
    parser.add_argument("--capture-timeout", type=float, default=25.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    args.output = str(output)
    try:
        report = asyncio.run(validate_live_chain(args))
    except Exception as exc:
        report = {
            "ok": False,
            "transport": "webrtc",
            "model": "quicktalk",
            "error": f"{type(exc).__name__}: {exc}",
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
