from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _even(value: int) -> int:
    value = max(2, int(value))
    return value - (value % 2)


def _resize_image(image: Image.Image, *, max_long_edge: int) -> Image.Image:
    fitted = image.convert("RGB")
    if max_long_edge > 0 and max(fitted.size) > max_long_edge:
        fitted.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
    width, height = fitted.size
    even_width = _even(width)
    even_height = _even(height)
    if (even_width, even_height) != fitted.size:
        fitted = fitted.resize((even_width, even_height), Image.Resampling.LANCZOS)
    return fitted


DEFAULT_ANIMATION: dict[str, Any] = {
    "mouth_center": [0.501, 0.381],
    "mouth_rx": 0.047,
    "mouth_ry": 0.014,
    "outer_lip": [
        [0.454, 0.374],
        [0.475, 0.363],
        [0.501, 0.358],
        [0.528, 0.363],
        [0.55, 0.374],
        [0.529, 0.393],
        [0.502, 0.4],
        [0.475, 0.393],
    ],
    "inner_mouth": [
        [0.466, 0.379],
        [0.487, 0.371],
        [0.502, 0.369],
        [0.518, 0.371],
        [0.538, 0.379],
        [0.519, 0.388],
        [0.502, 0.391],
        [0.485, 0.388],
    ],
    "left_eye_center": [0.421, 0.276],
    "right_eye_center": [0.579, 0.276],
    "eye_rx": 0.038,
    "eye_ry": 0.018,
}


def _phase_pulse(phase: float, center: float, width: float) -> float:
    distance = abs((phase - center + math.pi) % (2.0 * math.pi) - math.pi)
    if distance >= width:
        return 0.0
    value = 1.0 - distance / max(width, 1e-6)
    return value * value * (3.0 - 2.0 * value)


def _blend_patch(frame: np.ndarray, patch: np.ndarray, x1: int, y1: int, strength: float) -> None:
    h, w = patch.shape[:2]
    mask = np.zeros((h, w), dtype=np.float32)
    cv2.ellipse(mask, (w // 2, h // 2), (max(2, w // 2 - 1), max(2, h // 2 - 1)), 0, 0, 360, 1, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, min(w, h) / 7.0))
    mask = np.clip(mask[..., None] * strength, 0.0, 1.0)
    target = frame[y1:y1 + h, x1:x1 + w].astype(np.float32)
    frame[y1:y1 + h, x1:x1 + w] = np.clip(patch.astype(np.float32) * mask + target * (1.0 - mask), 0, 255).astype(np.uint8)


def _apply_eye_blink(frame: np.ndarray, *, phase: float) -> np.ndarray:
    height, width = frame.shape[:2]
    blink = max(_phase_pulse(phase, 1.18, 0.13), _phase_pulse(phase, 4.62, 0.11)) * 0.62
    if blink <= 0.01:
        return frame
    eye_rx = int(round(float(DEFAULT_ANIMATION["eye_rx"]) * width * 1.45))
    eye_ry = int(round(float(DEFAULT_ANIMATION["eye_ry"]) * height * 2.2))
    for center_name in ("left_eye_center", "right_eye_center"):
        center = DEFAULT_ANIMATION[center_name]
        cx = int(round(float(center[0]) * width))
        cy = int(round(float(center[1]) * height))
        x1 = max(0, cx - eye_rx)
        x2 = min(width, cx + eye_rx)
        y1 = max(0, cy - eye_ry)
        y2 = min(height, cy + eye_ry)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = frame[y1:y2, x1:x2]
        scaled_h = max(2, int(round(crop.shape[0] * (1.0 - blink * 0.42))))
        compressed = cv2.resize(crop, (crop.shape[1], scaled_h), interpolation=cv2.INTER_AREA)
        patch = cv2.GaussianBlur(crop, (0, 0), 0.45)
        yoff = max(0, (crop.shape[0] - scaled_h) // 2)
        patch[yoff:yoff + scaled_h, :] = compressed
        _blend_patch(frame, patch, x1, y1, blink)
    return frame


def _animation_metadata(width: int, height: int) -> dict[str, Any]:
    return {
        **DEFAULT_ANIMATION,
        "template_motion": {
            "mode": "quicktalk-source-micro-expression",
            "head_motion": "subpixel",
            "blink_frames": "two short blink pulses per template loop",
            "generated_in_backend": True,
            "frontend_overlay": False,
            "width": width,
            "height": height,
        },
    }


def _motion_frame(base_bgr: np.ndarray, index: int, total: int) -> np.ndarray:
    height, width = base_bgr.shape[:2]
    phase = 2.0 * np.pi * float(index) / float(max(1, total))
    scale = 1.004 + 0.002 * np.sin(phase)
    tx = 0.55 * np.sin(phase * 0.7)
    ty = 0.38 * np.cos(phase * 0.9)
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.08 * np.sin(phase * 0.5), scale)
    matrix[0, 2] += tx
    matrix[1, 2] += ty
    frame = cv2.warpAffine(
        base_bgr,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT101,
    )
    return _apply_eye_blink(frame, phase=phase)


def _write_template_video(path: Path, image: Image.Image, *, fps: int, seconds: float) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    base_rgb = np.asarray(image)
    base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)
    height, width = base_bgr.shape[:2]
    frame_count = max(24, int(round(float(fps) * max(1.0, float(seconds)))))
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(max(1, fps)),
        (int(width), int(height)),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Cannot open template video writer: {path}")
    try:
        for index in range(frame_count):
            writer.write(_motion_frame(base_bgr, index, frame_count))
    finally:
        writer.release()
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"Template video was not written: {path}")
    return frame_count


def prepare_asset(
    *,
    source_image: Path,
    out_dir: Path,
    avatar_id: str,
    name: str,
    max_long_edge: int,
    fps: int,
    template_seconds: float,
) -> None:
    image = Image.open(source_image)
    image.load()
    image = _resize_image(image, max_long_edge=max_long_edge)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    frames_dir = out_dir / "frames"
    source_dir = out_dir / "source"
    quicktalk_dir = out_dir / "quicktalk"
    frames_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    quicktalk_dir.mkdir(parents=True)

    copied_source = source_dir / f"source{source_image.suffix.lower() or '.png'}"
    shutil.copy2(source_image, copied_source)

    reference = out_dir / "reference.png"
    preview = out_dir / "preview.png"
    frame = frames_dir / "frame_00000.png"
    image.save(reference, format="PNG")
    image.save(preview, format="PNG")
    image.save(frame, format="PNG")

    template_video = quicktalk_dir / f"template_{image.width}x{image.height}.mp4"
    frame_count = _write_template_video(template_video, image, fps=fps, seconds=template_seconds)

    manifest: dict[str, Any] = {
        "id": avatar_id,
        "name": name,
        "model_type": "quicktalk",
        "fps": fps,
        "sample_rate": 16000,
        "width": image.width,
        "height": image.height,
        "version": "1.0",
        "metadata": {
            "description": "Preprocessed Lingjing QuickTalk avatar asset.",
            "idle_mode": "quicktalk-template",
            "reference_mode": "image",
            "source_image": str(copied_source.relative_to(out_dir)).replace("\\", "/"),
            "source_image_path": "reference.png",
            "source_image_hash": _sha256(reference),
            "preprocessed": True,
            "preprocess_version": 1,
            "mouth_polygon_source": "manual_lingjing_asset",
            "animation": _animation_metadata(image.width, image.height),
            "quicktalk": {
                "template_video": str(template_video.relative_to(out_dir)).replace("\\", "/"),
                "template_fps": fps,
                "template_frame_count": frame_count,
                "template_mode": "generated-from-authorized-reference-image-with-micro-expressions",
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a QuickTalk avatar bundle from an authorized reference image.")
    parser.add_argument("--source-image", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--avatar-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--max-long-edge", type=int, default=720)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--template-seconds", type=float, default=2.4)
    args = parser.parse_args()
    prepare_asset(
        source_image=args.source_image,
        out_dir=args.out,
        avatar_id=args.avatar_id,
        name=args.name,
        max_long_edge=max(2, args.max_long_edge),
        fps=max(1, args.fps),
        template_seconds=max(1.0, args.template_seconds),
    )


if __name__ == "__main__":
    main()
