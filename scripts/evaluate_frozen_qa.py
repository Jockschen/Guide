from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from server.quality_evaluation import (  # noqa: E402
    evaluate_answer,
    quality_run_payload,
    summarize_results,
)


DEFAULT_FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "frozen_scenic_qa.json"
DEFAULT_OUTPUT = ROOT / "reports" / "quality"


def _report_slug(fixture: dict[str, Any]) -> str:
    slug = str(fixture.get("report_slug") or "frozen-qa").strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("fixture report_slug must use lowercase letters, numbers, and hyphens")
    return slug


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Visitor-ID": "frozen-qa-evaluator",
        },
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _markdown(report: dict[str, Any]) -> str:
    status = "达到本地目标" if report["target_reached"] else "未达到本地目标"
    rows = []
    for index, item in enumerate(report["results"], start=1):
        rows.append(
            f"| {index} | {'通过' if item['passed'] else '失败'} | {item['question']} | "
            f"{item.get('latency_ms', 0):.0f} | {item.get('provider', '')} |"
        )
    return "\n".join(
        [
            f"# {report.get('report_title') or '冻结问答集准确率报告'}",
            "",
            f"- 数据集：`{report['dataset_version']}`",
            f"- 口径：{report['scope_label']}",
            f"- 结果：{report['passed']}/{report['total']}，{report['accuracy_percent']:.2f}%（{status}）",
            f"- 平均延迟：{report['average_latency_ms']} ms；P95：{report['p95_latency_ms']} ms",
            "- 边界：本报告只证明当前本地环境与冻结数据集的结果，不能替代评审专家的官方测试集评分。",
            "",
            "| # | 结果 | 问题 | 延迟(ms) | 回答链路 |",
            "| --- | --- | --- | ---: | --- |",
            *rows,
            "",
        ]
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    report_slug = _report_slug(fixture)
    cases = fixture["cases"][: args.limit or None]
    base_url = args.base_url.rstrip("/")
    results: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        try:
            response = _post_json(
                f"{base_url}/api/chat",
                {
                    "question": case["question"],
                    "guide_style": "knowledge",
                    "image_base64": None,
                },
                args.timeout,
            )
            data = response.get("data") or {}
            answer = str(data.get("answer") or "")
            sources = data.get("sources") or []
            evaluated = evaluate_answer(case, answer, sources)
            results.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "answer": answer,
                    "sources": sources,
                    "provider": data.get("provider") or "",
                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
                    **evaluated,
                }
            )
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            results.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "answer": "",
                    "sources": [],
                    "provider": "request-error",
                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
                    "passed": False,
                    "facts_passed": False,
                    "source_passed": False,
                    "error": str(exc),
                }
            )

    report = summarize_results(
        dataset_version=fixture["dataset_version"],
        results=results,
        runtime={"mode": "local-live-api", "base_url": base_url},
    )
    success_count = sum(
        1
        for item in results
        if not item.get("error") and str(item.get("provider") or "") != "request-error"
    )
    report["report_slug"] = report_slug
    report["report_title"] = str(fixture.get("report_title") or "冻结问答集准确率报告")
    report["success_count"] = success_count
    report["success_rate_percent"] = round((success_count / len(results) * 100.0) if results else 0.0, 2)
    if args.persist:
        try:
            saved = _post_json(
                f"{base_url}/api/admin/competition/quality-runs",
                quality_run_payload(report),
                args.timeout,
            )
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            report["persistence"] = {"ok": False, "error": str(exc)}
        else:
            report["persistence"] = {
                "ok": bool(saved.get("ok")),
                "run_id": (saved.get("data") or {}).get("id"),
            }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    md_text = _markdown(report)
    (output_dir / f"{report_slug}-{stamp}.json").write_text(json_text, encoding="utf-8")
    (output_dir / f"{report_slug}-{stamp}.md").write_text(md_text, encoding="utf-8")
    (output_dir / f"{report_slug}-latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / f"{report_slug}-latest.md").write_text(md_text, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the local scenic QA chain on a frozen evidence set.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--no-persist", action="store_false", dest="persist")
    parser.set_defaults(persist=True)
    args = parser.parse_args()
    report = run(args)
    print(json.dumps({key: report[key] for key in ("dataset_version", "passed", "total", "accuracy_percent", "target_reached")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
