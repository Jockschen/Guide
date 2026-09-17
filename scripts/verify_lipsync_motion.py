from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _load_animation(avatar_dir: Path | None) -> dict[str, Any]:
    if avatar_dir is None:
        return {}
    manifest = avatar_dir / "manifest.json"
    if not manifest.is_file():
        return {}
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return {}
    metadata = raw.get("metadata") if isinstance(raw, dict) else {}
    animation = metadata.get("animation") if isinstance(metadata, dict) else {}
    return animation if isinstance(animation, dict) else {}


def _mouth_roi(width: int, height: int, animation: dict[str, Any]) -> tuple[int, int, int, int]:
    polygon = animation.get("inner_mouth") or animation.get("outer_lip")
    if isinstance(polygon, list) and len(polygon) >= 3:
        points: list[tuple[float, float]] = []
        for point in polygon:
            if isinstance(point, list) and len(point) >= 2:
                points.append((float(point[0]) * width, float(point[1]) * height))
        if len(points) >= 3:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            pad_x = max(8.0, (max_x - min_x) * 0.28)
            pad_y = max(7.0, (max_y - min_y) * 0.45)
            x1 = max(0, int(round(min_x - pad_x)))
            x2 = min(width, int(round(max_x + pad_x)))
            y1 = max(0, int(round(min_y - pad_y)))
            y2 = min(height, int(round(max_y + pad_y)))
            if x2 > x1 and y2 > y1:
                return x1, y1, x2, y2

    center = animation.get("mouth_center")
    rx = float(animation.get("mouth_rx") or 0.06)
    ry = float(animation.get("mouth_ry") or 0.025)
    if isinstance(center, list) and len(center) >= 2:
        cx = float(center[0]) * width
        cy = float(center[1]) * height
    else:
        cx = width * 0.5
        cy = height * 0.46
    half_w = max(18.0, rx * width * 2.4)
    half_h = max(12.0, ry * height * 4.0)
    x1 = max(0, int(round(cx - half_w)))
    x2 = min(width, int(round(cx + half_w)))
    y1 = max(0, int(round(cy - half_h)))
    y2 = min(height, int(round(cy + half_h)))
    if x2 <= x1 or y2 <= y1:
        return 0, 0, width, height
    return x1, y1, x2, y2


def measure(video: Path, avatar_dir: Path | None = None, max_frames: int = 120) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video}")
    animation = _load_animation(avatar_dir)
    previous: np.ndarray | None = None
    mouth_deltas: list[float] = []
    full_deltas: list[float] = []
    frames = 0
    roi: tuple[int, int, int, int] | None = None
    try:
        while frames < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if roi is None:
                h, w = frame.shape[:2]
                roi = _mouth_roi(w, h, animation)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if previous is not None:
                x1, y1, x2, y2 = roi
                mouth_deltas.append(float(np.mean(cv2.absdiff(gray[y1:y2, x1:x2], previous[y1:y2, x1:x2]))))
                full_deltas.append(float(np.mean(cv2.absdiff(gray, previous))))
            previous = gray
            frames += 1
    finally:
        cap.release()
    mouth = np.asarray(mouth_deltas, dtype=np.float32)
    full = np.asarray(full_deltas, dtype=np.float32)
    return {
        "video": str(video),
        "frames": frames,
        "roi": list(roi or []),
        "mouth_mean_delta": round(float(mouth.mean()) if mouth.size else 0.0, 4),
        "mouth_max_delta": round(float(mouth.max()) if mouth.size else 0.0, 4),
        "full_mean_delta": round(float(full.mean()) if full.size else 0.0, 4),
        "moving_pairs": int(np.sum(mouth > 0.75)) if mouth.size else 0,
        "pairs": int(mouth.size),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify generated lip-sync video has visible mouth movement.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--avatar-dir")
    parser.add_argument("--min-mouth-mean-delta", type=float, default=0.65)
    parser.add_argument("--min-moving-pairs", type=int, default=3)
    parser.add_argument("--max-frames", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = measure(
        Path(args.video).expanduser().resolve(),
        Path(args.avatar_dir).expanduser().resolve() if args.avatar_dir else None,
        max_frames=max(2, args.max_frames),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["frames"] < 8:
        raise SystemExit("lip-sync video is too short to verify mouth motion")
    if result["mouth_mean_delta"] < args.min_mouth_mean_delta:
        raise SystemExit("mouth movement delta is below threshold")
    if result["moving_pairs"] < args.min_moving_pairs:
        raise SystemExit("not enough moving mouth frame pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
