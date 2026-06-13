#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


RESULT_START = "__MN_RESULT_START__"
RESULT_END = "__MN_RESULT_END__"


def read_input_payload() -> dict[str, Any]:
    input_file = os.getenv("MN_INPUT_FILE")
    if not input_file:
        return {}
    try:
        decoded = json.loads(Path(input_file).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def parse_video_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    sandbox = payload.get("sandbox") if isinstance(payload.get("sandbox"), dict) else {}
    raw_stdout = sandbox.get("stdout")
    if isinstance(raw_stdout, str) and raw_stdout.strip():
        try:
            parsed = json.loads(raw_stdout)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    direct = payload.get("analysis")
    return direct if isinstance(direct, dict) else {}


def report_markdown(analysis: dict[str, Any]) -> str:
    videos = analysis.get("videos") if isinstance(analysis.get("videos"), list) else []
    lines = [
        "# Safety Video Analysis Report",
        "",
        f"Model: {analysis.get('model') or 'unknown'}",
        f"Videos reviewed: {len(videos)}",
        "",
        "## Findings",
    ]
    if not videos:
        lines.append("- No staged videos were available for review.")
    for item in videos:
        if not isinstance(item, dict):
            continue
        size_mb = float(item.get("size_bytes") or 0) / (1024 * 1024)
        lines.append(
            f"- {item.get('logical_name')}: {item.get('safety_focus')} "
            f"({size_mb:.2f} MB, {item.get('media_type')})."
        )
    lines.extend(
        [
            "",
            "## Routing Check",
            f"Report model: {os.getenv('MN_LLM_MODEL') or 'unknown'}",
            f"Report provider: {os.getenv('MN_LLM_PROVIDER') or 'unknown'}",
        ]
    )
    return "\n".join(lines) + "\n"


def emit_result(payload: dict[str, Any], exit_code: int = 0) -> None:
    envelope = {
        "exit_code": exit_code,
        "stdout": json.dumps(payload, sort_keys=True),
        "stderr": "",
    }
    print(f"{RESULT_START}{json.dumps(envelope, sort_keys=True)}{RESULT_END}")


def main() -> int:
    incoming = read_input_payload()
    analysis = parse_video_analysis(incoming)
    markdown = report_markdown(analysis)
    Path("safety_video_report.md").write_text(markdown, encoding="utf-8")
    video_count = len(analysis.get("videos") or [])
    incoming_findings = analysis.get("actor_findings") if isinstance(analysis.get("actor_findings"), dict) else {}
    report_finding = {
        "actor_id": "report_generator",
        "role": "Safety report generator actor",
        "summary": f"Wrote a review-only safety video report for {video_count} staged video file(s).",
        "findings": [
            {
                "video_count": video_count,
                "report_path": "safety_video_report.md",
            }
        ],
        "risks": [] if video_count else ["no_video_findings_to_report"],
        "recommended_next_step": "Have a human safety reviewer confirm the report before operational use.",
        "confidence": 0.74 if video_count else 0.35,
    }
    actor_findings = {**incoming_findings, "report_generator": report_finding}
    analysis_usage = analysis.get("llm_usage") if isinstance(analysis.get("llm_usage"), dict) else {}
    result = {
        "schema": "otterdesk.safety_video_report.v1",
        "agent": "report_generator",
        "model": os.getenv("MN_LLM_MODEL") or "unknown",
        "provider": os.getenv("MN_LLM_PROVIDER") or "unknown",
        "video_count": video_count,
        "report_path": "safety_video_report.md",
        "report_markdown": markdown,
        "actor_findings": actor_findings,
        "llm_usage": {
            "provider": os.getenv("MN_LLM_PROVIDER") or analysis_usage.get("provider") or "unknown",
            "model": os.getenv("MN_LLM_MODEL") or analysis_usage.get("model") or "unknown",
            "calls": int(analysis_usage.get("calls") or 0),
            "fallback_calls": int(analysis_usage.get("fallback_calls") or 0),
        },
        "actor_activity": [
            *(
                analysis.get("actor_activity")
                if isinstance(analysis.get("actor_activity"), list)
                else []
            ),
            {
                "agent_id": "report_generator",
                "step_id": "report_generator",
                "status": "completed",
                "summary": report_finding["summary"],
            },
        ],
    }
    Path("safety_video_report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    emit_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
