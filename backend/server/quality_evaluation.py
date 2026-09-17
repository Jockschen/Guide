from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from pathlib import Path
import re
import statistics
import time
from typing import Any

from .qwen_client import call_qwen, qwen_available
from .retrieval import local_answer, retrieve


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "frozen_scenic_qa.json"
Answerer = Callable[[str], dict[str, Any]]


def _normalized(value: Any) -> str:
    text = str(value or "")
    # A factual evaluator should not mark the same whole-hour time wrong only
    # because one side writes ``9:00`` and the other writes ``9点``.
    text = re.sub(r"(?<!\d)0?(\d{1,2})\s*[:：]\s*00(?!\d)", r"\1点", text)
    text = re.sub(r"(?<!\d)0?(\d{1,2})\s*点\s*(?:00\s*分?)?(?!\d)", r"\1点", text)
    return re.sub(r"[\s，。；：、,.!?！？:;()（）\-—_]+", "", text).casefold()


def evaluate_answer(
    case: dict[str, Any],
    answer: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_answer = _normalized(answer)
    groups = case.get("required_fact_groups") or []
    fact_checks = [
        any(_normalized(term) in normalized_answer for term in group)
        for group in groups
    ]
    facts_passed = bool(fact_checks) and all(fact_checks)

    expected_source = _normalized(case.get("source_file"))
    source_values = [
        _normalized(source.get("source_file") or source.get("title"))
        for source in sources
    ]
    source_passed = not expected_source or any(
        expected_source in value or value in expected_source
        for value in source_values
        if value
    )
    return {
        "passed": facts_passed and source_passed,
        "facts_passed": facts_passed,
        "source_passed": source_passed,
        "fact_checks": fact_checks,
    }


def summarize_results(
    *,
    dataset_version: str,
    results: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    passed = sum(1 for item in results if item.get("passed"))
    total = len(results)
    latencies = [
        float(item["latency_ms"])
        for item in results
        if item.get("latency_ms") is not None
    ]
    sorted_latencies = sorted(latencies)
    p95_index = (
        max(0, min(len(sorted_latencies) - 1, round(len(sorted_latencies) * 0.95) - 1))
        if sorted_latencies
        else 0
    )
    return {
        "kind": "frozen_qa_accuracy",
        "dataset_version": dataset_version,
        "scope_label": "本地冻结问答集自测（非比赛官方评测）",
        "official_evaluation": False,
        "passed": passed,
        "total": total,
        "accuracy_percent": round((passed / total * 100.0) if total else 0.0, 2),
        "target_percent": 90.0,
        "target_reached": bool(total) and passed / total >= 0.9,
        "average_latency_ms": round(statistics.fmean(latencies), 2) if latencies else None,
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        "p95_latency_ms": round(sorted_latencies[p95_index], 2) if sorted_latencies else None,
        "runtime": runtime,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "results": results,
    }


def quality_run_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_version": report["dataset_version"],
        "accuracy": round(float(report["accuracy_percent"]) / 100.0, 6),
        "sample_count": int(report["total"]),
        "passed_count": int(report["passed"]),
        "sample_details": report.get("results") or [],
        "latency_ms": {
            "average": report.get("average_latency_ms") or 0.0,
            "median": report.get("median_latency_ms") or 0.0,
            "p95": report.get("p95_latency_ms") or 0.0,
        },
        "environment": report.get("runtime") or {},
        "official_evaluation": False,
        "official_evidence_reference": "",
    }


def answer_with_current_pipeline(question: str) -> dict[str, Any]:
    """Run the same retrieval and Qwen/local fallback used by the visitor chat."""

    chunks = retrieve(question, limit=5)
    provider = "local-retrieval"
    try:
        answer = call_qwen(question, chunks, guide_style="自然讲解")
        provider = "qwen"
    except Exception:
        answer = local_answer(question, chunks, guide_style="自然讲解")
        provider = "local-retrieval" if not qwen_available() else "local-retrieval-fallback"
    sources = [
        {
            "title": chunk["title"],
            "source_file": chunk["source_file"],
            "source_type": chunk["source_type"],
            "score": chunk["score"],
        }
        for chunk in chunks
    ]
    return {"answer": answer, "sources": sources, "provider": provider}


def run_frozen_evaluation(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    answerer: Answerer | None = None,
    limit: int = 0,
) -> dict[str, Any]:
    """Execute a frozen question set in-process and return an auditable report."""

    path = Path(fixture_path)
    fixture = json.loads(path.read_text(encoding="utf-8"))
    cases = list(fixture.get("cases") or [])
    if limit > 0:
        cases = cases[:limit]
    execute = answerer or answer_with_current_pipeline
    results: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        try:
            response = execute(str(case["question"]))
            answer = str(response.get("answer") or "")
            sources = list(response.get("sources") or [])
            evaluated = evaluate_answer(case, answer, sources)
            results.append(
                {
                    "id": case.get("id") or "",
                    "question": case["question"],
                    "answer": answer,
                    "sources": sources,
                    "provider": str(response.get("provider") or ""),
                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
                    **evaluated,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": case.get("id") or "",
                    "question": case.get("question") or "",
                    "answer": "",
                    "sources": [],
                    "provider": "evaluation-error",
                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
                    "passed": False,
                    "facts_passed": False,
                    "source_passed": False,
                    "fact_checks": [],
                    "error": str(exc),
                }
            )

    return summarize_results(
        dataset_version=str(fixture.get("dataset_version") or path.stem),
        results=results,
        runtime={
            "mode": "local-in-process",
            "pipeline": "current-chat-retrieval-qwen-with-local-fallback",
            "fixture": path.name,
        },
    )
