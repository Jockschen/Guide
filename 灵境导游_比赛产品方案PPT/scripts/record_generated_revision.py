from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


SKILL_SCRIPTS = Path(r"C:\Users\陈术\.codex\skills\codex-ppt\scripts")
sys.path.insert(0, str(SKILL_SCRIPTS))

from slide_run_state import (  # noqa: E402
    deck_dir_from_target,
    find_slide,
    locked_jobs,
    now_iso,
    rel_to_deck,
    resolve_deck_path,
    set_run_status,
    sha256_file,
    update_jobs_run_status,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deck")
    parser.add_argument("--slide", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--backend-used", required=True)
    parser.add_argument("--qa-note", required=True)
    parser.add_argument("--approval", required=True)
    args = parser.parse_args()

    deck_dir = deck_dir_from_target(args.deck)
    source = Path(args.source).resolve()
    if not source.is_file():
        raise SystemExit(f"Missing source: {source}")

    with locked_jobs(deck_dir) as jobs:
        slide = find_slide(jobs, args.slide)
        if slide.get("status") != "recorded":
            raise SystemExit(f"Revision requires recorded status; got {slide.get('status')}")
        old_result = slide.get("result") or {}
        revisions = list(old_result.get("revisions") or [])
        revisions.append({
            "selected_source": old_result.get("selected_source"),
            "final_image_sha256": old_result.get("final_image_sha256"),
            "qa_note": old_result.get("qa_note"),
            "replaced_at": now_iso(),
        })
        out_ref = slide.get("out") or f"origin_image/{slide['slide_id']}.png"
        target = resolve_deck_path(deck_dir, out_ref)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target:
            shutil.copy2(source, target)
        slide["result"] = {
            "agent_id": "user-directed-generated-revision",
            "backend_used": args.backend_used,
            "selected_source": str(source),
            "selected_source_sha256": sha256_file(source),
            "final_image": rel_to_deck(deck_dir, target),
            "final_image_sha256": sha256_file(target),
            "expected_backend": "built-in image tool",
            "expected_backend_labels": ["built-in image tool", "image_gen__imagegen"],
            "sample_generation_method_matched": True,
            "qa_note": args.qa_note,
            "user_revision": {
                "approved": True,
                "approval_text": args.approval,
                "recorded_at": now_iso(),
            },
            "revisions": revisions,
            "recorded_at": now_iso(),
        }
        update_jobs_run_status(jobs)
        run_status = jobs.get("run_status")
        slide_id = slide["slide_id"]

    set_run_status(deck_dir, run_status, f"{slide_id}: generated revision recorded")
    print(f"{slide_id} -> revised and recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
