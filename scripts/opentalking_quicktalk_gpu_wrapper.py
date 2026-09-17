from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run OpenTalking QuickTalk on GPU and accept valid mp4 output."
    )
    parser.add_argument("--asset-root", required=True)
    parser.add_argument("--template-video", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--bench", default="apps/cli/quicktalk_bench.py")
    return parser.parse_args()


def video_is_playable(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        import cv2

        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                return False
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ok, _frame = cap.read()
            return ok and frame_count > 0 and width > 0 and height > 0
        finally:
            cap.release()
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("OPENTALKING_QUICKTALK_DEVICE", args.device)
    env.setdefault("OPENTALKING_QUICKTALK_HUBERT_DEVICE", args.device)
    env.setdefault("OPENTALKING_QUICKTALK_FPS", "12")
    env.setdefault("OPENTALKING_QUICKTALK_MAX_TEMPLATE_SECONDS", "1.2")

    command = [
        sys.executable,
        args.bench,
        "--asset-root",
        args.asset_root,
        "--template-video",
        args.template_video,
        "--audio",
        args.audio,
        "--output",
        str(output),
        "--device",
        args.device,
    ]
    result = subprocess.run(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode == 0:
        return 0 if video_is_playable(output) else 1

    if video_is_playable(output):
        print(
            f"OpenTalking bench exited with {result.returncode}, "
            f"but generated a valid mp4: {output}",
            file=sys.stderr,
        )
        return 0
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
