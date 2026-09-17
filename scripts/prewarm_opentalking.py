from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Mapping
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from server.opentalking_session import (  # noqa: E402
    ActiveProfilePayload,
    OpenTalkingClientError,
    OpenTalkingSessionClient,
    SessionCapability,
    SessionResult,
)


class PrewarmClient(Protocol):
    async def capability(self, profile: ActiveProfilePayload) -> SessionCapability: ...

    async def create_session(
        self,
        profile: ActiveProfilePayload,
        *,
        user_id: str | None = None,
    ) -> SessionResult: ...

    async def get_session(self, session_id: str) -> Mapping[str, Any]: ...

    async def delete_session(self, session_id: str) -> SessionResult: ...


Sleep = Callable[[float], Awaitable[None]]


def _failure(stage: str, reason: str, action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "unavailable",
        "stage": stage,
        "reason": reason,
        "action": action,
    }


async def prewarm_session(
    client: PrewarmClient,
    profile: ActiveProfilePayload,
    *,
    wait_timeout: float = 90.0,
    poll_interval: float = 0.25,
    sleep: Sleep = asyncio.sleep,
) -> dict[str, Any]:
    """Warm the selected official model/avatar through HTTP only, then clean up."""

    capability = await client.capability(profile)
    if not capability.available:
        return _failure(
            "health",
            capability.reason or "OpenTalking session capability is unavailable",
            "Start the official OpenTalking API and verify GET /health before rerunning prewarm.",
        )

    session_id: str | None = None
    result: dict[str, Any]
    try:
        try:
            created = await client.create_session(profile, user_id="lingjing-prewarm")
        except OpenTalkingClientError as exc:
            return _failure(
                "session_create",
                str(exc),
                (
                    "OpenTalking responded but could not create a session. Verify its Redis connection, "
                    "session worker, selected avatar assets, and QuickTalk runtime, then rerun prewarm."
                ),
            )
        except Exception as exc:  # defensive CLI boundary; do not echo unknown secret-bearing text
            return _failure(
                "session_create",
                f"{type(exc).__name__}: OpenTalking session creation failed",
                (
                    "Verify the official OpenTalking service, Redis connection, session worker, "
                    "and selected avatar assets, then rerun prewarm."
                ),
            )

        session_id = created.session_id
        deadline = time.monotonic() + max(0.0, wait_timeout)
        last_state = created.status
        while True:
            try:
                state_payload = await client.get_session(session_id)
            except OpenTalkingClientError as exc:
                result = _failure(
                    "session_ready",
                    str(exc),
                    (
                        "Check the OpenTalking worker and Redis session state, plus QuickTalk CUDA/model "
                        "and avatar assets, then rerun prewarm."
                    ),
                )
                break
            except Exception as exc:
                result = _failure(
                    "session_ready",
                    f"{type(exc).__name__}: OpenTalking session state check failed",
                    (
                        "Check the OpenTalking worker and Redis session state, plus QuickTalk CUDA/model "
                        "and avatar assets, then rerun prewarm."
                    ),
                )
                break

            last_state = str(state_payload.get("state") or last_state or "unknown")
            if last_state in {"worker_ready", "ready", "speaking"}:
                result = {
                    "ok": True,
                    "status": "ready",
                    "stage": "complete",
                    "session_id": session_id,
                    "profile": {
                        "avatar_id": profile.avatar_id,
                        "model": profile.model,
                    },
                    "capability": capability.to_dict(),
                }
                break
            if time.monotonic() >= deadline:
                result = _failure(
                    "session_ready",
                    f"session did not reach ready state (last state: {last_state})",
                    (
                        "Inspect OpenTalking worker logs and verify QuickTalk CUDA/model/avatar assets and "
                        "Redis session state; increase --wait-timeout only if initialization is progressing."
                    ),
                )
                break
            await sleep(max(0.01, poll_interval))
    finally:
        if session_id is not None:
            try:
                await client.delete_session(session_id)
            except OpenTalkingClientError as exc:
                if "result" in locals():
                    result["cleanup_warning"] = str(exc)
                    result["cleanup_action"] = (
                        "Close the temporary OpenTalking session manually or restart the session worker."
                    )
            except Exception as exc:
                if "result" in locals():
                    result["cleanup_warning"] = f"{type(exc).__name__}: temporary session cleanup failed"
                    result["cleanup_action"] = (
                        "Close the temporary OpenTalking session manually or restart the session worker."
                    )

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prewarm the official OpenTalking session model and selected avatar.",
    )
    parser.add_argument(
        "--base-url",
        default=(
            os.environ.get("OPENTALKING_SESSION_BASE_URL", "").strip()
            or os.environ.get("OPENTALKING_BASE_URL", "").strip()
            or "http://127.0.0.1:8010"
        ),
    )
    parser.add_argument("--avatar-id", default=os.environ.get("OPENTALKING_AVATAR_ID", "lingjing-guide"))
    parser.add_argument("--model", default=os.environ.get("OPENTALKING_MODEL", "quicktalk"))
    parser.add_argument("--persona-id", default=os.environ.get("OPENTALKING_PERSONA_ID", ""))
    parser.add_argument(
        "--stt-provider",
        default=os.environ.get("OPENTALKING_SESSION_STT_PROVIDER", "funasr"),
        help="Official session bootstrap STT provider; external-audio default: funasr.",
    )
    parser.add_argument(
        "--tts-provider",
        default=os.environ.get("OPENTALKING_SESSION_TTS_PROVIDER", "edge"),
        help="Official session bootstrap TTS provider; external-audio default: edge.",
    )
    parser.add_argument("--tts-voice", default=os.environ.get("OPENTALKING_TTS_VOICE", ""))
    parser.add_argument("--tts-model", default=os.environ.get("OPENTALKING_TTS_MODEL", ""))
    parser.add_argument("--system-prompt", default="")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--wait-timeout", type=float, default=90.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        profile = ActiveProfilePayload(
            avatar_id=str(args.avatar_id).strip(),
            model=str(args.model).strip() or "quicktalk",
            persona_id=str(args.persona_id).strip() or None,
            stt_provider=str(args.stt_provider).strip() or "funasr",
            tts_provider=str(args.tts_provider).strip() or "edge",
            tts_voice=str(args.tts_voice).strip() or None,
            tts_model=str(args.tts_model).strip() or None,
            llm_system_prompt=str(args.system_prompt).strip() or None,
        )
        if not profile.avatar_id:
            raise ValueError("avatar id is empty")
        token = os.environ.get("OPENTALKING_API_TOKEN", "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        client = OpenTalkingSessionClient(
            str(args.base_url),
            timeout=float(args.timeout),
            event_timeout=max(float(args.timeout), 45.0),
            headers=headers,
            secret_values=[token] if token else [],
        )
    except (TypeError, ValueError) as exc:
        return _failure(
            "configuration",
            str(exc),
            "Provide a valid --base-url, --avatar-id, model, and positive timeout values.",
        )
    return await prewarm_session(
        client,
        profile,
        wait_timeout=float(args.wait_timeout),
        poll_interval=float(args.poll_interval),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except Exception as exc:  # final machine-readable CLI boundary
        result = _failure(
            "unexpected",
            f"{type(exc).__name__}: prewarm failed unexpectedly",
            "Inspect the OpenTalking API and worker logs, correct the reported dependency, and rerun prewarm.",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
