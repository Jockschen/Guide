from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OpenTalkingScriptTests(unittest.TestCase):
    def test_wav2lip_renderer_uses_real_opentalking_adapter(self) -> None:
        source = (ROOT / "scripts" / "opentalking_wav2lip_gpu_render.py").read_text(encoding="utf-8")

        self.assertIn("Wav2LipAdapter", source)
        self.assertIn("adapter.load_model(args.device)", source)
        self.assertIn("_resample_pcm_i16", source)
        self.assertIn("target_sample_rate: int = 16000", source)
        self.assertIn("OPENTALKING_WAV2LIP_MAX_SECONDS", source)
        self.assertIn("--max-seconds", source)
        self.assertIn('OPENTALKING_WAV2LIP_MAX_SECONDS", "0"', source)
        self.assertIn("_pad_frames_to_audio", source)
        self.assertIn("_log_event", source)
        self.assertIn("adapter.infer(features, avatar_state)", source)
        self.assertNotIn("OWoman.mp4", source)
        self.assertNotIn("avatar-driver-layer", source)

    def test_quicktalk_renderer_uses_real_opentalking_adapter(self) -> None:
        source = (ROOT / "scripts" / "opentalking_quicktalk_gpu_render.py").read_text(encoding="utf-8")

        self.assertIn("QuickTalkAdapter", source)
        self.assertIn("adapter.load_model(args.device)", source)
        self.assertIn("adapter.load_avatar(str(avatar_dir))", source)
        self.assertIn("adapter.extract_features_for_stream", source)
        self.assertIn("adapter.infer(features, avatar_state)", source)
        self.assertIn('OPENTALKING_QUICKTALK_MAX_SECONDS", "0"', source)
        self.assertIn("_pad_frames_to_audio", source)
        self.assertIn('"model": "quicktalk"', source)
        self.assertNotIn("OWoman.mp4", source)

    def test_quicktalk_renderer_has_visitor_speed_encode_profile(self) -> None:
        source = (ROOT / "scripts" / "opentalking_quicktalk_gpu_render.py").read_text(encoding="utf-8")

        self.assertIn("OPENTALKING_QUICKTALK_OUTPUT_MAX_SIDE", source)
        self.assertIn("OPENTALKING_QUICKTALK_X264_PRESET", source)
        self.assertIn("_resize_frames_for_output", source)
        self.assertIn('"-preset"', source)
        self.assertIn('"+faststart"', source)

    def test_quicktalk_prepare_script_writes_template_video_metadata(self) -> None:
        source = (ROOT / "scripts" / "prepare_quicktalk_avatar_asset.py").read_text(encoding="utf-8")

        self.assertIn("_write_template_video", source)
        self.assertIn("template_video", source)
        self.assertIn("template_", source)
        self.assertIn('"model_type": "quicktalk"', source)

    def test_motion_verifier_checks_mouth_roi(self) -> None:
        source = (ROOT / "scripts" / "verify_lipsync_motion.py").read_text(encoding="utf-8")

        self.assertIn("mouth_mean_delta", source)
        self.assertIn("mouth_max_delta", source)
        self.assertIn("moving_pairs", source)
        self.assertIn("manifest.json", source)


if __name__ == "__main__":
    unittest.main()
