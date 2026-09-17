from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "quality"
STRICT_STAGE_KEYS = (
    "asr_ms",
    "chat_ms",
    "tts_ms",
    "session_enqueue_ms",
    "first_valid_audio_ms",
    "first_visible_mouth_ms",
)


def summarize_timings(timings: dict[str, float | None], *, threshold_ms: float) -> dict[str, Any]:
    """Keep the original single-sample stage summary API for existing callers.

    New benchmark reports use ``summarize_sample`` and ``summarize_samples`` below,
    whose completeness contract additionally requires ASR and browser-observed
    visible mouth motion.
    """
    clean = {key: round(float(value), 2) for key, value in timings.items() if value is not None}
    total = round(sum(clean.values()), 2)
    measurement_complete = all(
        key in clean for key in ("chat_ms", "tts_ms", "session_enqueue_ms", "first_frame_ms")
    )
    return {
        "kind": "end_to_end_latency",
        "scope_label": "本地端到端延迟自测（非比赛官方评测）",
        "official_evaluation": False,
        "timings_ms": clean,
        "measured_total_ms": total,
        "target_ms": threshold_ms,
        "measurement_complete": measurement_complete,
        "within_target": measurement_complete and total < threshold_ms,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _finite_milliseconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, 2)


def _strict_timings(raw: dict[str, Any]) -> dict[str, float]:
    nested = raw.get("timings_ms") or raw.get("stages_ms")
    source = nested if isinstance(nested, dict) else raw
    timings: dict[str, float] = {}
    for key in STRICT_STAGE_KEYS:
        value = _finite_milliseconds(source.get(key))
        if value is not None:
            timings[key] = value
    return timings


def summarize_sample(
    raw: dict[str, Any],
    *,
    sample_id: str,
    run_kind: str,
    threshold_ms: float,
    source: str = "active-api",
) -> dict[str, Any]:
    timings = _strict_timings(raw)
    missing_stages = [key for key in STRICT_STAGE_KEYS if key not in timings]
    nested = raw.get("timings_ms") or raw.get("stages_ms")
    nested_source = nested if isinstance(nested, dict) else {}
    end_to_end_ms = _finite_milliseconds(raw.get("end_to_end_ms", nested_source.get("end_to_end_ms")))
    if end_to_end_ms is None:
        missing_stages.append("end_to_end_ms")
    asr_provider = str(raw.get("asr_provider") or "").strip().lower()
    tts_provider = str(raw.get("tts_provider") or "").strip().lower()
    driver = str(raw.get("driver") or "").strip().lower()
    if not asr_provider or asr_provider == "mock":
        missing_stages.append("real_asr_provider")
    if not tts_provider or tts_provider == "mock":
        missing_stages.append("real_tts_provider")
    if driver != "session_stream":
        missing_stages.append("session_stream_driver")
    success = bool(raw.get("success", not raw.get("error"))) and not any(
        key in missing_stages
        for key in ("real_asr_provider", "real_tts_provider", "session_stream_driver")
    )
    measurement_complete = success and not missing_stages
    stage_sum_ms = round(sum(timings.values()), 2)
    measured_total_ms = end_to_end_ms if end_to_end_ms is not None else 0.0
    result: dict[str, Any] = {
        "sample_id": sample_id,
        "run_kind": "cold" if run_kind == "cold" else "hot",
        "source": source,
        "success": success,
        "timings_ms": timings,
        "missing_stages": missing_stages,
        "measurement_complete": measurement_complete,
        "measured_total_ms": measured_total_ms,
        "end_to_end_ms": end_to_end_ms,
        "stage_sum_ms": stage_sum_ms,
        "within_target": measurement_complete and measured_total_ms < threshold_ms,
        "asr_provider": asr_provider,
        "tts_provider": tts_provider,
        "driver": driver,
    }
    for key in ("answer_length", "tts_audio_ready", "session_id", "question", "error", "failure_reason", "collected_at"):
        if key in raw:
            result[key] = raw[key]
    if raw.get("first_frame_ms") is not None:
        result["legacy_first_frame_ignored"] = True
    return result


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (len(ordered) - 1) * fraction
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[lower], 2)
    weight = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 2)


def _statistics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(samples)
    successful = sum(1 for sample in samples if sample["success"])
    complete = [sample for sample in samples if sample["measurement_complete"]]
    within_target = sum(1 for sample in samples if sample["within_target"])
    totals = [float(sample["measured_total_ms"]) for sample in complete]
    return {
        "sample_count": total,
        "successful_samples": successful,
        "complete_samples": len(complete),
        "success_rate_percent": round(successful * 100.0 / total, 2) if total else 0.0,
        "complete_rate_percent": round(len(complete) * 100.0 / total, 2) if total else 0.0,
        "within_target_rate_percent": round(within_target * 100.0 / total, 2) if total else 0.0,
        "latency_ms": {
            "p50": _percentile(totals, 0.50),
            "p95": _percentile(totals, 0.95),
        },
    }


def summarize_samples(
    samples: list[dict[str, Any]],
    *,
    threshold_ms: float,
    requested_samples: int,
) -> dict[str, Any]:
    statistics = _statistics(samples)
    measurement_complete = (
        requested_samples > 0
        and len(samples) == requested_samples
        and statistics["complete_samples"] == requested_samples
    )
    p95 = statistics["latency_ms"]["p95"]
    groups = {
        kind: _statistics([sample for sample in samples if sample["run_kind"] == kind])
        for kind in ("cold", "hot")
    }
    stage_statistics = {}
    for key in STRICT_STAGE_KEYS:
        values = [float(sample["timings_ms"][key]) for sample in samples if key in sample["timings_ms"]]
        stage_statistics[key] = {
            "sample_count": len(values),
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
        }
    report: dict[str, Any] = {
        "kind": "end_to_end_latency",
        "scope_label": "本地端到端延迟自测（非比赛官方评测）",
        "official_evaluation": False,
        "target_ms": threshold_ms,
        "requested_samples": requested_samples,
        **statistics,
        "measurement_complete": measurement_complete,
        "within_target": bool(
            measurement_complete
            and p95 is not None
            and float(p95) < threshold_ms
            and statistics["success_rate_percent"] == 100.0
        ),
        "groups": groups,
        "stage_statistics_ms": stage_statistics,
        "samples": samples,
        "percentile_method": "linear_interpolation",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if len(samples) == 1:
        report["timings_ms"] = samples[0]["timings_ms"]
        report["measured_total_ms"] = samples[0]["measured_total_ms"]
        for key in ("question", "answer_length", "tts_audio_ready", "session_id"):
            if key in samples[0]:
                report[key] = samples[0][key]
    return report


def load_sample_file(path: str | Path, *, threshold_ms: float) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_samples = payload.get("samples") if isinstance(payload, dict) else payload
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("The sample JSON must contain a non-empty samples list")
    samples: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_samples):
        if not isinstance(raw, dict):
            raise ValueError(f"Sample {index + 1} is not an object")
        samples.append(
            summarize_sample(
                raw,
                sample_id=str(raw.get("sample_id") or f"browser-{index + 1:03d}"),
                run_kind=str(raw.get("run_kind") or ("cold" if index == 0 else "hot")),
                threshold_ms=threshold_ms,
                source=str(raw.get("source") or "browser-session"),
            )
        )
    return samples


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "X-Visitor-ID": "e2e-benchmark"},
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _markdown(report: dict[str, Any]) -> str:
    stage_rows = []
    for name, stats in report["stage_statistics_ms"].items():
        p50 = "-" if stats["p50"] is None else f"{stats['p50']:.2f}"
        p95 = "-" if stats["p95"] is None else f"{stats['p95']:.2f}"
        stage_rows.append(f"| {name} | {stats['sample_count']} | {p50} | {p95} |")
    p50 = report["latency_ms"]["p50"]
    p95 = report["latency_ms"]["p95"]
    conclusion = (
        "低于 5 秒本地目标"
        if report["within_target"]
        else "尚未形成完整的低于 5 秒证据"
    )
    return "\n".join(
        [
            "# 端到端延迟报告",
            "",
            f"- 口径：{report['scope_label']}",
            f"- 样本：{report['sample_count']}/{report['requested_samples']}；完整率：{report['complete_rate_percent']:.2f}%",
            f"- 成功率：{report['success_rate_percent']:.2f}%；达标率：{report['within_target_rate_percent']:.2f}%",
            f"- 端到端 P50 / P95：{p50 if p50 is not None else '-'} / {p95 if p95 is not None else '-'} ms",
            f"- 结论：{conclusion}",
            "- 边界：每个严格样本必须来自真实 ASR/TTS 与 session_stream，并同时记录首个真实音频播放和首个可见口型；权威总时延直接取浏览器端到端时间，不相加可能并行的阶段诊断值。",
            "",
            "| 阶段 | 有效样本 | P50(ms) | P95(ms) |",
            "| --- | ---: | ---: | ---: |",
            *stage_rows,
            "",
        ]
    )


def _collect_api_sample(args: argparse.Namespace, *, index: int, base_url: str) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    timings: dict[str, float | None] = {"chat_ms": None, "tts_ms": None, "session_enqueue_ms": None}

    started = time.perf_counter()
    chat = _post_json(
        f"{base_url}/api/chat",
        {"question": args.question, "guide_style": "knowledge", "image_base64": None},
        args.timeout,
    )
    timings["chat_ms"] = (time.perf_counter() - started) * 1000.0
    answer = str((chat.get("data") or {}).get("answer") or "")

    started = time.perf_counter()
    tts = _post_json(
        f"{base_url}/api/tts/synthesize",
        {"text": answer, "voice": args.voice},
        args.timeout,
    )
    timings["tts_ms"] = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    session = _post_json(
        f"{base_url}/api/avatar/sessions",
        {"client_id": "quality-benchmark", "purpose": "external-audio"},
        args.timeout,
    )
    timings["session_enqueue_ms"] = (time.perf_counter() - started) * 1000.0

    raw: dict[str, Any] = {
        **timings,
        "success": True,
        "question": args.question,
        "answer_length": len(answer),
        "tts_audio_ready": bool((tts.get("data") or {}).get("audio_url")),
        "session_id": (session.get("data") or session).get("session_id"),
    }
    legacy_first_frame = getattr(args, "first_frame_ms", None)
    if legacy_first_frame is not None:
        raw["first_frame_ms"] = legacy_first_frame
    return summarize_sample(
        raw,
        sample_id=f"api-{index + 1:03d}",
        run_kind="cold" if index == 0 else "hot",
        threshold_ms=args.threshold_ms,
        source="active-api",
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    sample_file = getattr(args, "sample_file", None)
    if sample_file:
        samples = load_sample_file(sample_file, threshold_ms=args.threshold_ms)
        requested_samples = len(samples)
        collection_mode = "browser-session-import"
    else:
        requested_samples = int(getattr(args, "samples", 1))
        if requested_samples < 1:
            raise ValueError("--samples must be at least 1")
        samples = []
        for index in range(requested_samples):
            try:
                samples.append(_collect_api_sample(args, index=index, base_url=base_url))
            except Exception as exc:
                samples.append(
                    summarize_sample(
                        {"success": False, "error": f"{type(exc).__name__}: {exc}"},
                        sample_id=f"api-{index + 1:03d}",
                        run_kind="cold" if index == 0 else "hot",
                        threshold_ms=args.threshold_ms,
                        source="active-api",
                    )
                )
        collection_mode = "active-api-partial"

    report = summarize_samples(
        samples,
        threshold_ms=args.threshold_ms,
        requested_samples=requested_samples,
    )
    report["runtime"] = {
        "mode": collection_mode,
        "base_url": base_url,
        "voice": args.voice,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    md_text = _markdown(report)
    (output_dir / f"e2e-latency-{stamp}.json").write_text(json_text, encoding="utf-8")
    (output_dir / f"e2e-latency-{stamp}.md").write_text(md_text, encoding="utf-8")
    (output_dir / "e2e-latency-latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / "e2e-latency-latest.md").write_text(md_text, encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure the local question-to-WebRTC-first-frame chain.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default="九龙灌浴今天有哪些演出时间？")
    parser.add_argument("--voice", default="gentle")
    parser.add_argument(
        "--first-frame-ms",
        type=float,
        help="Deprecated compatibility input; recorded as ignored and never completes a strict sample.",
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument(
        "--sample-file",
        "--samples-json",
        dest="sample_file",
        help="Browser/real-session per-sample JSON containing all strict timing stages.",
    )
    parser.add_argument("--threshold-ms", type=float, default=5000.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    return parser


def main() -> None:
    report = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "sample_count": report["sample_count"],
                "p50_ms": report["latency_ms"]["p50"],
                "p95_ms": report["latency_ms"]["p95"],
                "success_rate_percent": report["success_rate_percent"],
                "measurement_complete": report["measurement_complete"],
                "within_target": report["within_target"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
