from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class OpenTalkingStartupContractTests(unittest.TestCase):
    def test_env_documents_session_first_4060_profile(self) -> None:
        env = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("OPENTALKING_SESSION_ENABLED=1", env)
        self.assertIn("OPENTALKING_SESSION_BASE_URL=http://127.0.0.1:8210", env)
        self.assertIn("OPENTALKING_SESSION_MODEL=quicktalk", env)
        self.assertIn("OPENTALKING_SESSION_AVATAR_ID=lingjing-guide-quicktalk", env)
        self.assertIn("OPENTALKING_QUICKTALK_FPS=25", env)
        self.assertIn("OPENTALKING_QUICKTALK_SLICE_LEN=28", env)
        self.assertIn("OPENTALKING_QUICKTALK_RENDER_CHUNK_MS=500", env)
        self.assertIn("OPENTALKING_PREWARM_AVATARS=lingjing-guide-quicktalk", env)
        self.assertIn("OPENTALKING_REMOTE_PROVIDER_BASE_URL=", env)

    def test_windows_launcher_starts_official_unified_service(self) -> None:
        source = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        stop_source = (ROOT / "scripts" / "stop.ps1").read_text(encoding="utf-8")

        self.assertIn("apps.unified.main", source)
        self.assertIn('Start-HiddenService -Name "opentalking-session"', source)
        self.assertIn("OPENTALKING_SESSION_AUTOSTART", source)
        self.assertIn("OPENTALKING_SESSION_BASE_URL", source)
        self.assertIn("prewarm_opentalking.py", source)
        self.assertIn("--avatar-id", source)
        self.assertIn('Start-HiddenService -Name "opentalking-prewarm"', source)
        self.assertNotIn('OPENTALKING_PREWARM_AVATARS = "lingjing-guide-quicktalk"', source)
        self.assertNotIn("& $opentalkingSessionPython $prewarmScript", source)
        self.assertIn("/health", source)
        self.assertIn("apps.unified.main", stop_source)
        self.assertIn("opentalking_session_port", stop_source)
        self.assertIn("8210", stop_source)

    def test_vendored_worker_does_not_initialize_disabled_memory_runtime(self) -> None:
        consumer = (
            ROOT
            / "third_party"
            / "opentalking"
            / "opentalking"
            / "runtime"
            / "task_consumer.py"
        ).read_text(encoding="utf-8")

        self.assertIn("memory_scope if memory_scope.enabled else None", consumer)
        try_index = consumer.index("try:\n        runner = _create_runner", consumer.index("async def _do_init"))
        create_index = consumer.index("runner = _create_runner", consumer.index("async def _do_init"))
        self.assertLess(try_index, create_index)

    def test_quicktalk_prewarm_accepts_official_worker_ready_state(self) -> None:
        prewarm = (ROOT / "scripts" / "prewarm_opentalking.py").read_text(encoding="utf-8")

        self.assertIn('{"worker_ready", "ready", "speaking"}', prewarm)

    def test_quicktalk_cache_never_uses_output_template_as_its_source(self) -> None:
        prepare_cache = (
            ROOT
            / "third_party"
            / "opentalking"
            / "apps"
            / "cli"
            / "prepare_cache.py"
        ).read_text(encoding="utf-8")

        self.assertIn("reuse_existing_template", prepare_cache)
        self.assertIn("and not reuse_existing_template", prepare_cache)


if __name__ == "__main__":
    unittest.main()
