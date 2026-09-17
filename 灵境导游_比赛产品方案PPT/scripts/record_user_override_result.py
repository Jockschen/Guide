from __future__ import annotations

import argparse
from pathlib import Path
import sys


SKILL_SCRIPTS = Path(r"C:\Users\陈术\.codex\skills\codex-ppt\scripts")
sys.path.insert(0, str(SKILL_SCRIPTS))

from slide_run_state import (  # noqa: E402
    deck_dir_from_target,
    find_slide,
    locked_jobs,
    now_iso,
    rel_to_deck,
    set_run_status,
    sha256_file,
    update_jobs_run_status,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deck")
    parser.add_argument("--slide", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--qa-note", required=True)
    parser.add_argument("--approval", required=True)
    args = parser.parse_args()

    deck_dir = deck_dir_from_target(args.deck)
    source = Path(args.source).resolve()
    if not source.is_file():
        raise SystemExit(f"Missing source: {source}")
    try:
        source.relative_to(deck_dir)
    except ValueError as exc:
        raise SystemExit("Override result must already live inside deck directory") from exc

    with locked_jobs(deck_dir) as jobs:
        slide = find_slide(jobs, args.slide)
        current_result = slide.get("result") or {}
        is_existing_user_override = bool((current_result.get("user_override") or {}).get("approved"))
        allowed = {"blocked", "pending", "dispatched"}
        if is_existing_user_override:
            allowed.add("recorded")
        if slide.get("status") not in allowed:
            raise SystemExit(f"Unexpected status: {slide.get('status')}")
        previous_blocker = slide.get("blocker")
        slide["resolved_blocker"] = previous_blocker
        slide["blocker"] = None
        slide["result"] = {
            "agent_id": "user-approved-workflow-exception",
            "backend_used": "deterministic exact screenshot composition",
            "selected_source": str(source),
            "selected_source_sha256": sha256_file(source),
            "final_image": rel_to_deck(deck_dir, source),
            "final_image_sha256": sha256_file(source),
            "expected_backend": None,
            "expected_backend_labels": ["user-approved product screenshot exception"],
            "sample_generation_method_matched": False,
            "qa_note": args.qa_note,
            "user_override": {
                "approved": True,
                "approval_text": args.approval,
                "recorded_at": now_iso(),
            },
            "recorded_at": now_iso(),
        }
        slide["status"] = "recorded"
        update_jobs_run_status(jobs)
        run_status = jobs.get("run_status")
        slide_id = slide["slide_id"]

    set_run_status(deck_dir, run_status, f"{slide_id}: user-approved exact screenshot composition recorded")
    print(f"{slide_id} -> recorded (user-approved workflow exception)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
