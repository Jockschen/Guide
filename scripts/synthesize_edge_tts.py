from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import tempfile
import wave

import av
import edge_tts


async def synthesize(*, text_file: Path, output: Path, voice: str, rate: str, volume: str) -> None:
    text = text_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("speech text is empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as media_file:
        media_path = Path(media_file.name)
    try:
        await edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume).save(str(media_path))
        container = av.open(str(media_path))
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=24_000)
        pcm_parts: list[bytes] = []
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                pcm_parts.append(converted.to_ndarray().astype("<i2", copy=False).tobytes())
        for converted in resampler.resample(None):
            pcm_parts.append(converted.to_ndarray().astype("<i2", copy=False).tobytes())
        container.close()
        pcm = b"".join(pcm_parts)
        if not pcm:
            raise RuntimeError("Edge TTS returned empty audio")
        with wave.open(str(output), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24_000)
            wav_file.writeframes(pcm)
    finally:
        media_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a PCM WAV with Edge Chinese TTS.")
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    parser.add_argument("--rate", default="+0%")
    parser.add_argument("--volume", default="+0%")
    args = parser.parse_args()
    asyncio.run(synthesize(text_file=args.text_file, output=args.output, voice=args.voice, rate=args.rate, volume=args.volume))


if __name__ == "__main__":
    main()
