from __future__ import annotations

import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server import voice


class VoiceAdapterTests(unittest.TestCase):
    def test_edge_tts_generates_pcm_wav_with_real_rate_and_volume_controls(self) -> None:
        original_settings = voice.settings
        original_run = voice.subprocess.run
        original_new_audio_path = voice._new_audio_path
        captured: dict[str, object] = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "edge.wav"
            voice.settings = replace(original_settings, tts_provider="edge")
            voice._new_audio_path = lambda prefix="tts", suffix=".wav": output_path  # type: ignore[assignment]

            def fake_run(command, *args, **kwargs):  # type: ignore[no-untyped-def]
                captured["command"] = command
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24_000)
                    wav_file.writeframes(b"\x00\x00" * 240)
                return SimpleNamespace(stdout=b"", stderr=b"")

            voice.subprocess.run = fake_run  # type: ignore[assignment]
            try:
                result = voice.synthesize_tts(
                    "欢迎来到灵山胜境",
                    voice="gentle",
                    speed=1.2,
                    volume=0.65,
                )
            finally:
                voice._new_audio_path = original_new_audio_path  # type: ignore[assignment]
                voice.subprocess.run = original_run  # type: ignore[assignment]
                voice.settings = original_settings

        command = [str(item) for item in captured["command"]]  # type: ignore[index]
        self.assertEqual(result["provider"], "edge")
        self.assertTrue(str(result["audio_url"]).endswith("edge.wav"))
        self.assertIn("zh-CN-XiaoxiaoNeural", command)
        self.assertIn("--rate=+20%", command)
        self.assertIn("--volume=-35%", command)

    def test_vivo_gateway_signature_matches_official_example(self) -> None:
        headers = voice._vivo_gateway_headers(
            method="GET",
            path="/service/search/adminByPoint",
            canonical_query="location=116.45831%2C39.876169&token=111",
            app_id="1080389454",
            app_key="XpurLJTrKSuAGoIq",
            timestamp="1629255133",
            nonce="le1qqjex",
        )

        self.assertEqual(headers["X-AI-GATEWAY-APP-ID"], "1080389454")
        self.assertEqual(headers["X-AI-GATEWAY-SIGNATURE"], "/fZaIjhXe9lLpwehh1luXq5iijk6g+uZxK3bWe74F8o=")

    def test_vivo_tts_uses_signed_gateway_headers_and_writes_pcm_wav(self) -> None:
        class FakeABNF:
            OPCODE_CLOSE = 8
            OPCODE_TEXT = 1
            OPCODE_BINARY = 2

        class FakeWebSocket:
            def __init__(self) -> None:
                self.frames = [
                    (FakeABNF.OPCODE_TEXT, json.dumps({"error_code": 0, "error_msg": "connect success"}).encode()),
                    (
                        FakeABNF.OPCODE_TEXT,
                        json.dumps(
                            {
                                "error_code": 0,
                                "error_msg": "success",
                                "data": {
                                    "audio": base64.b64encode(b"\x01\x00\x02\x00").decode(),
                                    "status": 2,
                                },
                            }
                        ).encode(),
                    ),
                ]
                self.sent: list[str] = []

            def settimeout(self, timeout: int) -> None:
                self.timeout = timeout

            def recv_data(self, control_frame: bool):  # type: ignore[no-untyped-def]
                return self.frames.pop(0)

            def send(self, data: str) -> None:
                self.sent.append(data)

            def close(self) -> None:
                pass

        fake_websocket = FakeWebSocket()
        captured: dict[str, object] = {}

        def fake_create_connection(url: str, *, header: list[str], timeout: int):  # type: ignore[no-untyped-def]
            captured.update(url=url, header=header, timeout=timeout)
            return fake_websocket

        original_settings = voice.settings
        original_require_websocket = voice._require_websocket
        original_new_audio_path = voice._new_audio_path
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "vivo.wav"
            voice.settings = replace(
                original_settings,
                vivo_app_id="test-app-id",
                vivo_app_key="test-app-key",
                vivo_tts_url="wss://api-ai.vivo.com.cn/tts",
            )
            voice._require_websocket = lambda: (FakeABNF, fake_create_connection)  # type: ignore[assignment]
            voice._new_audio_path = lambda prefix="tts", suffix=".wav": output_path  # type: ignore[assignment]
            try:
                result = voice.synthesize_vivo_tts("欢迎", voice="yige")
            finally:
                voice._new_audio_path = original_new_audio_path  # type: ignore[assignment]
                voice._require_websocket = original_require_websocket  # type: ignore[assignment]
                voice.settings = original_settings

            with wave.open(str(output_path), "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 24_000)
                self.assertEqual(wav_file.readframes(2), b"\x01\x00\x02\x00")

        request_headers = list(captured["header"])  # type: ignore[arg-type]
        self.assertTrue(any(item.startswith("X-AI-GATEWAY-APP-ID: test-app-id") for item in request_headers))
        self.assertTrue(any(item.startswith("X-AI-GATEWAY-SIGNATURE: ") for item in request_headers))
        self.assertFalse(any(item.lower().startswith("authorization:") for item in request_headers))
        self.assertEqual(result["provider"], "vivo")

    def test_normalize_spoken_text_reads_clock_times_naturally(self) -> None:
        spoken = voice.normalize_spoken_text("九龙灌浴表演时间为 **10:00-10:30**，入园 08:05 后可前往。")

        self.assertIn("十点到十点三十分", spoken)
        self.assertIn("八点零五分", spoken)
        self.assertNotIn("10:00", spoken)

    def test_default_tts_falls_back_when_cosyvoice_is_not_ready(self) -> None:
        original_settings = voice.settings
        voice.settings = replace(
            original_settings,
            tts_provider="cosyvoice",
            cosyvoice_base_url="",
            cosyvoice_model_dir="",
        )
        try:
            result = voice.synthesize_tts("欢迎来到灵山胜境")
        finally:
            voice.settings = original_settings

        self.assertEqual(result["provider"], "mock")
        self.assertIsNone(result["audio_url"])
        self.assertGreater(len(result["visemes"]), 0)

    def test_vivo_tts_without_key_falls_back_to_mock(self) -> None:
        original_settings = voice.settings
        voice.settings = replace(original_settings, tts_provider="vivo", vivo_app_key="")
        try:
            result = voice.synthesize_tts("欢迎来到灵山胜境")
        finally:
            voice.settings = original_settings

        self.assertEqual(result["provider"], "mock")

    def test_vivo_voice_presets_map_to_documented_speakers(self) -> None:
        original_settings = voice.settings
        original_voice = os.environ.get("VIVO_TTS_VOICE_STORY")
        original_engine = os.environ.get("VIVO_TTS_ENGINE_STORY")
        os.environ["VIVO_TTS_VOICE_STORY"] = "F245_natural"
        os.environ["VIVO_TTS_ENGINE_STORY"] = "tts_humanoid_lam"
        voice.settings = replace(original_settings, vivo_tts_voice="yige", vivo_tts_engine_id="short_audio_synthesis_jovi")
        try:
            config = voice._provider_voice_config("story")
        finally:
            if original_voice is None:
                os.environ.pop("VIVO_TTS_VOICE_STORY", None)
            else:
                os.environ["VIVO_TTS_VOICE_STORY"] = original_voice
            if original_engine is None:
                os.environ.pop("VIVO_TTS_ENGINE_STORY", None)
            else:
                os.environ["VIVO_TTS_ENGINE_STORY"] = original_engine
            voice.settings = original_settings

        self.assertEqual(config["voice"], "F245_natural")
        self.assertEqual(config["engineid"], "tts_humanoid_lam")

    def test_vivo_tts_chunks_long_text_under_request_limit(self) -> None:
        chunks = voice._split_tts_chunks("欢迎来到灵山胜境。" * 260, max_bytes=1800)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 1800 for chunk in chunks))

    def test_default_asr_falls_back_when_funasr_is_not_ready(self) -> None:
        original_settings = voice.settings
        voice.settings = replace(
            original_settings,
            asr_provider="funasr",
            funasr_base_url="",
            funasr_model_dir="",
        )
        try:
            result = voice.transcribe_asr(b"not-a-real-audio", filename="question.webm", content_type="audio/webm")
        finally:
            voice.settings = original_settings

        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["text"], "九龙灌浴表演时间是什么？")

    def test_vivo_asr_uses_pcm_recording_when_key_is_configured(self) -> None:
        original_settings = voice.settings
        original_transcribe = voice.transcribe_vivo_asr
        called = {"value": False}
        voice.settings = replace(original_settings, asr_provider="vivo", vivo_app_key="test-key")

        def fake_transcribe(pcm_data: bytes) -> dict[str, str]:
            called["value"] = True
            self.assertEqual(pcm_data, b"pcm-audio")
            return {"provider": "vivo", "text": "灵山胜境在哪里", "message": "ok"}

        voice.transcribe_vivo_asr = fake_transcribe  # type: ignore[assignment]
        try:
            result = voice.transcribe_asr(b"pcm-audio", filename="question.pcm", content_type="audio/pcm")
        finally:
            voice.transcribe_vivo_asr = original_transcribe  # type: ignore[assignment]
            voice.settings = original_settings

        self.assertTrue(called["value"])
        self.assertEqual(result["provider"], "vivo")
        self.assertEqual(result["text"], "灵山胜境在哪里")

    def test_sherpa_onnx_asr_command_template_returns_text(self) -> None:
        original_settings = voice.settings
        original_run = voice.subprocess.run
        voice.settings = replace(
            original_settings,
            asr_provider="sherpa_onnx",
            sherpa_onnx_asr_base_url="",
            sherpa_onnx_asr_command="fake-asr --input {input}",
            sherpa_onnx_asr_exe="",
            sherpa_onnx_asr_extra_args="",
        )

        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(stdout='{"text":"九龙灌浴在哪里"}'.encode("utf-8"), stderr=b"")

        voice.subprocess.run = fake_run  # type: ignore[assignment]
        try:
            result = voice.transcribe_asr(b"audio", filename="question.wav", content_type="audio/wav")
        finally:
            voice.subprocess.run = original_run  # type: ignore[assignment]
            voice.settings = original_settings

        self.assertEqual(result["provider"], "sherpa_onnx")
        self.assertEqual(result["text"], "九龙灌浴在哪里")

    def test_sherpa_onnx_tts_command_template_writes_audio(self) -> None:
        original_settings = voice.settings
        original_run = voice.subprocess.run
        voice.settings = replace(
            original_settings,
            tts_provider="sherpa_onnx",
            sherpa_onnx_tts_base_url="",
            sherpa_onnx_tts_command='fake-tts --text "{text_file}" --out "{output}"',
            sherpa_onnx_tts_exe="",
            sherpa_onnx_tts_extra_args="",
        )

        def fake_run(command, *args, **kwargs):  # type: ignore[no-untyped-def]
            output_path = Path(command[command.index("--out") + 1])
            output_path.write_bytes(b"RIFF0000WAVE")
            return SimpleNamespace(stdout=b"", stderr=b"")

        voice.subprocess.run = fake_run  # type: ignore[assignment]
        try:
            result = voice.synthesize_tts("欢迎来到灵山胜境")
        finally:
            voice.subprocess.run = original_run  # type: ignore[assignment]
            voice.settings = original_settings

        self.assertEqual(result["provider"], "sherpa_onnx")
        self.assertTrue(str(result["audio_url"]).startswith("/static/audio/sherpa-onnx-"))


if __name__ == "__main__":
    unittest.main()
