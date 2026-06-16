#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


BLUEPRINT_ID = "personal_income_tax_expert"


def main() -> int:
    run_dir = Path(os.environ.get("MN_RUN_DIR") or "").expanduser()
    run_id = os.environ.get("MN_RUN_ID") or run_dir.name
    if not str(run_dir) or run_dir.name in {"", "."}:
        runs_root = Path(os.environ.get("MN_RUNS_ROOT") or "~/.mn/runs").expanduser()
        run_dir = runs_root / run_id

    events_path = run_dir / "events.jsonl"
    job_result = _latest_job_completed_result(events_path)
    runner_result = _find_runner_result(job_result)
    final_artifact = _final_artifact_from_result(runner_result)

    if not final_artifact:
        _write_status(run_dir, {"ok": False, "warning": f"No final artifact found in {events_path}"})
        print(f"No Personal Income Tax Expert final artifact found in {events_path}; nothing to materialize.")
        return 0

    runner_result = runner_result if isinstance(runner_result, dict) else {"final_artifact": final_artifact}
    final_artifact = dict(final_artifact)
    output_files, output_warnings = _write_output_folder_artifacts(final_artifact, runner_result, run_id)
    if output_files:
        final_artifact["output_files"] = output_files
        runner_result["output_files"] = output_files
    if output_warnings:
        existing = [str(item) for item in _as_list(final_artifact.get("output_warnings"))]
        final_artifact["output_warnings"] = _dedupe(existing + output_warnings)

    runner_result["final_artifact"] = final_artifact
    runner_result.setdefault("blueprint", BLUEPRINT_ID)
    run = runner_result.setdefault("run", {})
    if isinstance(run, dict):
        run.update(
            {
                "run_id": run_id,
                "run_dir": str(run_dir),
                "status": "completed",
                "ended_at": _utc_now_iso(),
            }
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "result.json", runner_result)
    _write_json(run_dir / "final_artifact.json", final_artifact)
    _write_json(
        run_dir / "run.json",
        {
            "run_id": run_id,
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "ended_at": _utc_now_iso(),
            "run_dir": str(run_dir),
            "result_path": str(run_dir / "result.json"),
            "final_artifact_path": str(run_dir / "final_artifact.json"),
        },
    )
    _write_status(run_dir, {"ok": True, "output_files": output_files, "warnings": output_warnings})
    print(f"Materialized Personal Income Tax Expert outputs in {run_dir}.")
    return 0


def _latest_job_completed_result(events_path: Path) -> Any:
    if not events_path.exists():
        return None
    result = None
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "job_completed":
            result = event.get("result")
    return result


def _find_runner_result(value: Any, depth: int = 0, seen: set[int] | None = None) -> dict[str, Any] | None:
    if depth > 12 or value is None:
        return None
    if seen is None:
        seen = set()
    if isinstance(value, str):
        decoded = _try_json(value)
        return _find_runner_result(decoded, depth + 1, seen) if decoded is not None else None
    if isinstance(value, list):
        for item in value:
            found = _find_runner_result(item, depth + 1, seen)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    marker = id(value)
    if marker in seen:
        return None
    seen.add(marker)

    final_artifact = value.get("final_artifact") or value.get("finalArtifact")
    if isinstance(final_artifact, dict) and final_artifact:
        return value
    if value.get("type") == "prepared_1040_tax_packet" and isinstance(value.get("prepared_form_1040"), dict):
        return {"final_artifact": value}

    for key in ("output", "result", "last_message", "lastMessage", "sandbox", "payload", "data", "logs"):
        found = _find_runner_result(value.get(key), depth + 1, seen)
        if found:
            return found
    for item in value.values():
        found = _find_runner_result(item, depth + 1, seen)
        if found:
            return found
    return None


def _final_artifact_from_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    artifact = result.get("final_artifact") or result.get("finalArtifact")
    if isinstance(artifact, dict) and artifact:
        return artifact
    if result.get("type") == "prepared_1040_tax_packet" and isinstance(result.get("prepared_form_1040"), dict):
        return result
    return None


def _write_output_folder_artifacts(
    final_artifact: dict[str, Any],
    runner_result: dict[str, Any],
    run_id: str,
) -> tuple[list[dict[str, str]], list[str]]:
    output_dir = _output_folder(runner_result, final_artifact)
    output_files: list[dict[str, str]] = []
    warnings: list[str] = []
    if output_dir is None:
        return output_files, warnings

    stem = _safe_filename(run_id if run_id.startswith(BLUEPRINT_ID) else f"{BLUEPRINT_ID}-{run_id}")
    json_path = output_dir / f"{stem}-final-artifact.json"
    markdown_path = output_dir / f"{stem}-report.md"
    pdf_path = output_dir / f"{stem}-tax-review-packet.pdf"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_files = [
            {"kind": "final_artifact_json", "path": str(json_path)},
            {"kind": "report_markdown", "path": str(markdown_path)},
        ]
        _write_json(json_path, final_artifact)
        markdown_path.write_text(_render_markdown(final_artifact), encoding="utf-8")
    except OSError as exc:
        return [], [f"Could not write output folder artifacts to {output_dir}: {exc}"]

    try:
        _write_pdf(final_artifact, pdf_path)
        output_files.append({"kind": "tax_review_packet_pdf", "path": str(pdf_path)})
        _remove_pdf_skip_warning(final_artifact)
        _write_json(json_path, final_artifact)
        markdown_path.write_text(_render_markdown(final_artifact), encoding="utf-8")
    except ModuleNotFoundError as exc:
        _write_basic_pdf(final_artifact, pdf_path)
        output_files.append({"kind": "tax_review_packet_pdf", "path": str(pdf_path)})
        warnings.append(f"PDF review packet used the built-in renderer because reportlab is unavailable: {exc}")
    except OSError as exc:
        warnings.append(f"PDF review packet could not be written to {pdf_path}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive for host PDF renderer differences
        try:
            _write_basic_pdf(final_artifact, pdf_path)
            output_files.append({"kind": "tax_review_packet_pdf", "path": str(pdf_path)})
            warnings.append(f"PDF review packet used the built-in renderer after reportlab failed: {exc}")
        except OSError as fallback_exc:
            warnings.append(f"PDF review packet could not be rendered: {exc}; built-in renderer also failed: {fallback_exc}")
    return output_files, warnings


def _output_folder(runner_result: dict[str, Any], final_artifact: dict[str, Any]) -> Path | None:
    config = runner_result.get("config") if isinstance(runner_result.get("config"), dict) else {}
    outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
    folder = outputs.get("folder_path") or os.environ.get("MN_OUTPUT_FOLDER")
    if not folder:
        for item in _as_list(final_artifact.get("output_files")):
            if isinstance(item, dict) and item.get("path"):
                return Path(str(item["path"])).expanduser().parent
        folder = "outputs/personal_income_tax_expert"
    return Path(str(folder)).expanduser()


def _render_markdown(final_artifact: dict[str, Any]) -> str:
    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    review = final_artifact.get("review") if isinstance(final_artifact.get("review"), dict) else {}
    manager = final_artifact.get("manager_review") if isinstance(final_artifact.get("manager_review"), dict) else {}
    summary = final_artifact.get("document_summary") if isinstance(final_artifact.get("document_summary"), dict) else {}
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}
    warnings = _as_list(review.get("warnings"))
    questions = _as_list(prepared.get("questions_for_user"))
    flags = _as_list(prepared.get("schedule_review_flags"))
    next_steps = _as_list(final_artifact.get("next_steps"))

    lines = [
        f"# {final_artifact.get('title') or 'Prepared Form 1040 Draft'}",
        "",
        f"**Draft warning:** {final_artifact.get('draft_warning') or 'Draft review packet only.'}",
        "",
        str(final_artifact.get("advisor_message") or "").strip(),
        "",
        "## Draft Form 1040 Line Map",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in line_map.items())
    lines.extend(["", "## Document Summary", "", f"- Document count: {summary.get('document_count', 0)}"])
    doc_types = summary.get("document_types") if isinstance(summary.get("document_types"), dict) else {}
    lines.extend(f"- {key}: {value}" for key, value in doc_types.items())
    lines.extend(["", "## Review Warnings", ""])
    lines.extend(f"- {item}" for item in (warnings or ["None"]))
    lines.extend(["", "## Schedule Review Flags", ""])
    lines.extend(f"- {item}" for item in (flags or ["None"]))
    lines.extend(["", "## Open Questions", ""])
    lines.extend(f"- {item}" for item in (questions or ["None"]))
    lines.extend(["", "## Manager Review", ""])
    lines.append(f"- Review status: {manager.get('review_status', 'manager_review_required')}")
    lines.append(f"- Signoff: {manager.get('manager_signoff', 'not_approved_for_filing')}")
    lines.extend(["", "## Next Steps", ""])
    lines.extend(f"- {item}" for item in (next_steps or ["Review the packet with the taxpayer or a qualified preparer."]))
    lines.extend(["", "This is a draft review packet, not a filed tax return.", ""])
    return "\n".join(lines)


def _write_basic_pdf(final_artifact: dict[str, Any], path: Path) -> None:
    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    review = final_artifact.get("review") if isinstance(final_artifact.get("review"), dict) else {}
    manager = final_artifact.get("manager_review") if isinstance(final_artifact.get("manager_review"), dict) else {}
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}
    lines = [
        str(final_artifact.get("title") or "Prepared Form 1040 Draft"),
        "",
        f"Draft warning: {final_artifact.get('draft_warning') or 'Draft review packet only.'}",
        str(final_artifact.get("advisor_message") or ""),
        "",
        "Draft Form 1040 Line Map",
    ]
    lines.extend(f"{key}: {value}" for key, value in line_map.items())
    lines.extend(["", "Review Warnings"])
    lines.extend(str(item) for item in (_as_list(review.get("warnings")) or ["None"]))
    lines.extend(["", "Manager Review"])
    lines.append(f"Review status: {manager.get('review_status', 'manager_review_required')}")
    lines.append(f"Signoff: {manager.get('manager_signoff', 'not_approved_for_filing')}")
    lines.extend(["", "This packet is not filing-ready until all open items are reviewed."])
    _write_basic_pdf_lines(path, lines)


def _write_basic_pdf_lines(path: Path, lines: list[str]) -> None:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap_pdf_line(line))
    pages = [wrapped[index : index + 48] for index in range(0, max(len(wrapped), 1), 48)] or [[]]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids: list[int] = []
    next_id = 4
    for page_index, page_lines in enumerate(pages, start=1):
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        content_lines = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
        for text in page_lines:
            content_lines.append(f"({_pdf_literal(text)}) Tj")
            content_lines.append("T*")
        content_lines.append(f"(Page {page_index} of {len(pages)}) Tj")
        content_lines.append("ET")
        content = "\n".join(content_lines).encode("latin-1", errors="replace")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(payload))
        payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
        payload.extend(objects[object_id])
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(payload)


def _wrap_pdf_line(value: Any, *, width: int = 92) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return [""]
    words = text.split(" ")
    result: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            result.append(current)
        current = word[:width]
        remainder = word[width:]
        while remainder:
            result.append(current)
            current = remainder[:width]
            remainder = remainder[width:]
    if current:
        result.append(current)
    return result or [""]


def _pdf_literal(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf(final_artifact: dict[str, Any], path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    warning_style = ParagraphStyle(
        "DraftWarning",
        parent=styles["BodyText"],
        textColor=colors.HexColor("#8A4B00"),
        backColor=colors.HexColor("#FFF3D4"),
        borderColor=colors.HexColor("#D28A00"),
        borderWidth=0.75,
        borderPadding=6,
        spaceAfter=10,
    )
    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    review = final_artifact.get("review") if isinstance(final_artifact.get("review"), dict) else {}
    manager = final_artifact.get("manager_review") if isinstance(final_artifact.get("manager_review"), dict) else {}
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}

    story: list[Any] = [
        Paragraph(_pdf_text(final_artifact.get("title") or "Prepared Form 1040 Draft"), styles["Title"]),
        Paragraph(_pdf_text(final_artifact.get("draft_warning") or "Draft review packet only."), warning_style),
        Paragraph(_pdf_text(final_artifact.get("advisor_message") or ""), styles["BodyText"]),
        Spacer(1, 0.18 * inch),
        Paragraph("Draft Form 1040 Line Map", styles["Heading2"]),
        _pdf_table([["Line", "Draft Value"], *[[_pdf_text(k), _pdf_text(v)] for k, v in line_map.items()]]),
        Spacer(1, 0.12 * inch),
        Paragraph("Review Warnings", styles["Heading2"]),
    ]
    story.extend(_pdf_bullets(_as_list(review.get("warnings")) or ["None"], styles["BodyText"]))
    story.append(Paragraph("Manager Review And Signoff", styles["Heading2"]))
    story.append(
        _pdf_table(
            [
                ["Review status", _pdf_text(manager.get("review_status", "manager_review_required"))],
                ["Signoff", _pdf_text(manager.get("manager_signoff", "not_approved_for_filing"))],
            ]
        )
    )
    story.append(Paragraph("Reviewer signoff: ________________________________", styles["BodyText"]))
    story.append(Paragraph("Date: ____________________", styles["BodyText"]))
    story.append(Paragraph("This packet is not filing-ready until all open items are reviewed.", warning_style))

    doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=0.55 * inch, leftMargin=0.55 * inch)
    doc.build(story)


def _pdf_table(rows: list[list[Any]]) -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, hAlign="LEFT", colWidths=[260, 220])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C7D1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _pdf_bullets(items: list[Any], style: Any) -> list[Any]:
    from reportlab.platypus import Paragraph

    return [Paragraph(f"- {_pdf_text(item)}", style) for item in items]


def _pdf_text(value: Any) -> str:
    return escape(str(value or ""))


def _try_json(value: str) -> Any:
    text = value.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _remove_pdf_skip_warning(final_artifact: dict[str, Any]) -> None:
    warnings = [
        str(item)
        for item in _as_list(final_artifact.get("output_warnings"))
        if "PDF review packet was skipped" not in str(item)
    ]
    if warnings:
        final_artifact["output_warnings"] = warnings
    else:
        final_artifact.pop("output_warnings", None)


def _write_status(run_dir: Path, payload: dict[str, Any]) -> None:
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        state_payload = dict(payload)
        state_payload.setdefault("status", "completed" if state_payload.get("ok") else "failed")
        state_payload.setdefault("materialized_at", _utc_now_iso())
        materialized_path = run_dir / "post_launch_materialized.json"
        _write_json(materialized_path, state_payload)
        state_file = os.environ.get("MN_POST_LAUNCH_STATE_FILE")
        if state_file:
            state_path = Path(state_file).expanduser()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            if state_path.resolve() != materialized_path.resolve():
                _write_json(state_path, state_payload)
    except OSError:
        pass


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return safe or f"{BLUEPRINT_ID}-report"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    sys.exit(main())
