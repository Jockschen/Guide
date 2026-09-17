from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

import cv2
import numpy as np

from opentalking.core.types.frames import AudioChunk
from opentalking.models.quicktalk.adapter import QuickTalkAdapter
from opentalking.models.quicktalk.runtime_v2 import ensure_ffmpeg, maybe_mkdir


def _resample_pcm_i16(pcm: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or pcm.size == 0:
        return pcm.astype(np.int16, copy=False)
    duration = float(pcm.shape[0]) / float(source_rate)
    target_count = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0, max(0, pcm.shape[0] - 1), num=target_count, dtype=np.float32)
    target = np.interp(source_positions, np.arange(pcm.shape[0], dtype=np.float32), pcm.astype(np.float32))
    return np.clip(np.rint(target), -32768, 32767).astype(np.int16)


def _log_event(stage: str, **fields: object) -> None:
    print(json.dumps({"stage": stage, **fields}, ensure_ascii=False), flush=True)


def _read_wav_i16(path: Path, target_sample_rate: int = 16000, max_seconds: float = 0.0) -> AudioChunk:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        sampwidth = wav_file.getsampwidth()
        frames = wav_file.getnframes()
        raw = wav_file.readframes(frames)
    if sampwidth != 2:
        raise ValueError(f"Only 16-bit wav is supported, got sampwidth={sampwidth}")
    pcm = np.frombuffer(raw, dtype="<i2")
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)
    pcm = _resample_pcm_i16(pcm.astype(np.int16, copy=False), sample_rate, target_sample_rate)
    if max_seconds > 0:
        max_samples = max(1, int(round(max_seconds * target_sample_rate)))
        if pcm.shape[0] > max_samples:
            pcm = pcm[:max_samples]
    duration_ms = float(pcm.shape[0]) / float(target_sample_rate) * 1000.0
    return AudioChunk(data=pcm.astype(np.int16, copy=False), sample_rate=target_sample_rate, duration_ms=duration_ms)


def _wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        sample_rate = wav_file.getframerate()
    return float(frames) / float(sample_rate) if sample_rate > 0 else 0.0


def _quicktalk_encode_profile() -> tuple[int, str, str]:
    raw_max_side = os.getenv("OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE", "540").strip()
    try:
        max_side = max(0, int(raw_max_side))
    except ValueError:
        max_side = 540
    preset = os.getenv("OPENTALKING_QUICKTALK_X264_PRESET", "veryfast").strip() or "veryfast"
    crf = os.getenv("OPENTALKING_QUICKTALK_X264_CRF", "23").strip() or "23"
    return max_side, preset, crf


def _resize_frames_for_output(frames: list[np.ndarray], max_side: int) -> list[np.ndarray]:
    if not frames or max_side <= 0:
        return frames
    height, width = frames[0].shape[:2]
    longest_edge = max(height, width)
    if longest_edge <= max_side:
        return frames
    scale = float(max_side) / float(longest_edge)
    target_width = max(2, int(round(width * scale)) // 2 * 2)
    target_height = max(2, int(round(height * scale)) // 2 * 2)
    return [cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA) for frame in frames]


def _open_ffmpeg_writer(
    fps: float,
    width: int,
    height: int,
    frame_count: int,
    output: Path,
    preset: str,
    crf: str,
) -> subprocess.Popen:
    maybe_mkdir(output.parent)
    cmd = [
        ensure_ffmpeg(),
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:g}",
        "-i",
        "pipe:0",
        "-frames:v",
        str(frame_count),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-tune",
        "zerolatency",
        "-crf",
        crf,
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def _pad_frames_to_audio(frames: list[np.ndarray], fps: float, audio: Path) -> list[np.ndarray]:
    if not frames:
        return frames
    duration_seconds = _wav_duration_seconds(audio)
    target_count = max(len(frames), int(np.ceil(duration_seconds * max(1.0, fps))))
    missing = target_count - len(frames)
    if missing <= 0:
        return frames
    return [*frames, *[frames[-1].copy() for _ in range(missing)]]


def _write_video(frames: list[np.ndarray], fps: float, audio: Path, output: Path) -> None:
    if not frames:
        raise RuntimeError("OpenTalking QuickTalk produced no frames.")
    max_side, preset, crf = _quicktalk_encode_profile()
    frames = _resize_frames_for_output(_pad_frames_to_audio(frames, fps, audio), max_side)
    height, width = frames[0].shape[:2]
    video_only = output.with_name(f"{output.stem}.video-only.mp4")
    video_only.unlink(missing_ok=True)
    proc = _open_ffmpeg_writer(fps, width, height, len(frames), video_only, preset, crf)
    assert proc.stdin is not None
    try:
        for frame in frames:
            proc.stdin.write(np.ascontiguousarray(frame[:, :, :3]).tobytes())
    finally:
        proc.stdin.close()
    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr is not None else ""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with code {rc}: {stderr.strip()}")
    mux_cmd = [
        ensure_ffmpeg(),
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_only),
        "-i",
        str(audio),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output),
    ]
    muxed = subprocess.run(mux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    video_only.unlink(missing_ok=True)
    if muxed.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed with code {muxed.returncode}: {muxed.stderr.strip()}")


def _video_stats(path: Path) -> dict[str, object]:
    cap = cv2.VideoCapture(str(path))
    try:
        opened = cap.isOpened()
        ok, _frame = cap.read() if opened else (False, None)
        return {
            "opened": opened,
            "first_frame": ok,
            "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if opened else 0,
            "fps": float(cap.get(cv2.CAP_PROP_FPS)) if opened else 0.0,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if opened else 0,
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if opened else 0,
            "bytes": path.stat().st_size if path.exists() else 0,
        }
    finally:
        cap.release()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a real OpenTalking QuickTalk video on GPU.")
    parser.add_argument("--avatar-dir", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-seconds", type=float, default=float(os.getenv("OPENTALKING_QUICKTALK_MAX_SECONDS", "0")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    avatar_dir = Path(args.avatar_dir).expanduser().resolve()
    audio = Path(args.audio).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    started = time.perf_counter()
    _log_event("start", device=args.device, avatar_dir=str(avatar_dir), audio=str(audio), max_seconds=args.max_seconds)
    adapter = QuickTalkAdapter()
    adapter.load_model(args.device)
    _log_event("model_loaded", seconds=round(time.perf_counter() - started, 3))
    avatar_state = adapter.load_avatar(str(avatar_dir))
    _log_event("avatar_loaded", fps=float(max(1, int(avatar_state.fps))))
    audio_chunk = _read_wav_i16(audio, max_seconds=args.max_seconds)
    _log_event("audio_loaded", duration_ms=round(audio_chunk.duration_ms, 1), sample_rate=audio_chunk.sample_rate)
    features = adapter.extract_features_for_stream(audio_chunk, avatar_state)
    _log_event(
        "features_extracted",
        reps=len(features.reps),
        render_reps=len(features.render_reps or features.reps),
        seconds=round(time.perf_counter() - started, 3),
    )
    predictions = adapter.infer(features, avatar_state)
    frames = [
        adapter.compose_frame(avatar_state, index, prediction).data
        for index, prediction in enumerate(predictions)
    ]
    fps = float(max(1, int(avatar_state.fps)))
    _log_event("frames_composed", frames=len(frames), fps=fps)
    _write_video(frames, fps, audio, output)
    stats = _video_stats(output)
    if not stats["opened"] or not stats["first_frame"] or int(stats["frames"]) <= 0:
        raise RuntimeError(f"Generated video is not playable: {output}")
    print(
        json.dumps(
            {
                "ok": True,
                "model": "quicktalk",
                "device": args.device,
                "avatar_dir": str(avatar_dir),
                "audio": str(audio),
                "output": str(output),
                "render_seconds": round(time.perf_counter() - started, 3),
                "prediction_frames": len(frames),
                **stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
