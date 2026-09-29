"""Deterministic source packets and the full catalog task list.

Partitions frozen UTF-8 source into bounded line/offset ranges (never dropping
text, even for one huge line or non-BMP unicode) and derives the complete
ordered review task list: source-scan tasks, 150 aspect-analysis tasks, 150
independent counterevidence/challenge tasks, 23 section-synthesis tasks, and a
final executive synthesis.  Also builds bounded per-task prompts and validates
dynamic followup proposals.  No source is executed.
"""

from __future__ import annotations

import hashlib

DEFAULT_CHUNK_BYTES = 24000
DEFAULT_PROMPT_BYTES = 60000
DEFAULT_MAX_TASKS = 1024
MAX_FOLLOWUPS_TOTAL = 64
FOLLOWUP_MAX_DEPTH = 2

APPLICABILITY = ("applicable", "not_applicable", "undetermined")
COVERAGE = ("complete_for_stated_scope", "partial", "not_analyzed", "blocked")
CLAIM_TYPES = ("observed", "derived", "inferred", "assumed", "proposed")
CONFIDENCE = ("high", "medium", "low", "insufficient_evidence")


def _packet_id(snapshot_id: str, path: str, start: int, end: int) -> str:
    digest = hashlib.sha256(
        f"{snapshot_id}\n{path}\n{start}:{end}".encode("utf-8")
    ).hexdigest()
    return f"pkt-{digest[:16]}"


def chunk_source(
    snapshot_id, path, text, file_sha256, max_bytes=DEFAULT_CHUNK_BYTES
) -> list:
    """Split one frozen source file into bounded packets.

    Packets carry ``{packet_id, path, sha256, start_line, end_line,
    start_offset, end_offset, byte_len, text}`` with character offsets into the
    original string.  Splits prefer line boundaries; a single line longer than
    ``max_bytes`` is split by UTF-8 size without breaking a code point
    (Python ``str`` slicing is code-point safe).  Concatenating packet texts in
    order reproduces the input exactly; empty files yield no packets.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 4:
        raise ValueError("max_bytes must be at least four")
    if not text:
        return []
    lines: list[tuple[str, int]] = []  # (line_text, lineno)
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        lines.append((line, lineno))
    if not lines and text:  # defensive: splitlines can be empty only for ""
        lines.append((text, 1))
    packets, current, current_bytes = [], [], 0
    start_offset, offset, start_line = 0, 0, 1

    def flush(end_offset, end_line):
        nonlocal current, current_bytes, start_offset, start_line
        if not current:
            return
        chunk_text = "".join(current)
        packets.append(
            {
                "packet_id": _packet_id(snapshot_id, path, start_offset, end_offset),
                "path": path,
                "sha256": file_sha256,
                "start_line": start_line,
                "end_line": end_line,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "byte_len": current_bytes,
                "text": chunk_text,
            }
        )
        current, current_bytes = [], 0
        start_offset, start_line = end_offset, end_line + 1

    for line, lineno in lines:
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > max_bytes:
            flush(offset, lineno - 1)
            # Split the huge line character by character, accumulating bytes.
            piece, piece_bytes, piece_start = [], 0, offset
            for char in line:
                char_bytes = len(char.encode("utf-8"))
                if piece and piece_bytes + char_bytes > max_bytes:
                    piece_text = "".join(piece)
                    packets.append(
                        {
                            "packet_id": _packet_id(
                                snapshot_id,
                                path,
                                piece_start,
                                piece_start + len(piece_text),
                            ),
                            "path": path,
                            "sha256": file_sha256,
                            "start_line": lineno,
                            "end_line": lineno,
                            "start_offset": piece_start,
                            "end_offset": piece_start + len(piece_text),
                            "byte_len": piece_bytes,
                            "text": piece_text,
                        }
                    )
                    offset = piece_start + len(piece_text)
                    piece, piece_bytes, piece_start = [], 0, offset
                piece.append(char)
                piece_bytes += char_bytes
            current = piece
            current_bytes = piece_bytes
            start_offset, start_line = piece_start, lineno
            offset = piece_start + len("".join(piece))
            flush(offset, lineno)
            continue
        if current and current_bytes + line_bytes > max_bytes:
            flush(offset, lineno - 1)
        if not current:
            start_offset, start_line = offset, lineno
        current.append(line)
        current_bytes += line_bytes
        offset += len(line)
    flush(offset, lines[-1][1] if lines else 0)
    return packets


def chunk_snapshot(snapshot: dict, max_bytes=DEFAULT_CHUNK_BYTES) -> list:
    """Chunk every source file in snapshot order; packet order is deterministic."""
    packets = []
    for path in snapshot["inventory"]:
        record = snapshot["sources"][path]
        packets.extend(
            chunk_source(
                snapshot["snapshot_id"],
                path,
                record["text"],
                record["sha256"],
                max_bytes,
            )
        )
    return packets


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _fit_text(value: str, budget: int) -> tuple[str, int]:
    """Truncate to a UTF-8 byte budget; returns (text, omitted_bytes)."""
    if _utf8_len(value) <= budget:
        return value, 0
    encoded = value.encode("utf-8")[:budget]
    text = encoded.decode("utf-8", errors="ignore")
    return text, _utf8_len(value) - _utf8_len(text)


def build_full_task_list(
    catalog: dict, packets: list, max_tasks=DEFAULT_MAX_TASKS
) -> tuple[list, dict]:
    """Build the ordered task list and explicit omission coverage.

    Order: source scans, aspect analyses, challenges, section syntheses,
    executive synthesis.  When the executable count would exceed ``max_tasks``,
    source-scan packets beyond the budget are omitted (recorded explicitly, never
    silently dropped from coverage).  Aspect/section/executive tasks are never
    implicitly dropped.  Returns ``(tasks, omitted)`` where ``omitted`` has
    ``omitted_packets``, ``omitted_packet_paths`` and ``truncated``.
    """
    aspect_ids = [a for s in catalog["sections"] for a in s["aspect_ids"]]
    section_numbers = [s["number"] for s in catalog["sections"]]
    fixed = 2 * len(aspect_ids) + len(section_numbers) + 1
    scan_budget = max(0, max_tasks - fixed)
    kept_packets = packets[:scan_budget]
    omitted_packets = packets[scan_budget:]
    tasks = [
        {
            "task_id": f"scan-{i + 1:04d}",
            "kind": "source_scan",
            "packet_id": p["packet_id"],
            "path": p["path"],
        }
        for i, p in enumerate(kept_packets)
    ]
    tasks += [
        {"task_id": f"analysis-{a}", "kind": "aspect_analysis", "aspect_id": a}
        for a in aspect_ids
    ]
    tasks += [
        {"task_id": f"challenge-{a}", "kind": "aspect_challenge", "aspect_id": a}
        for a in aspect_ids
    ]
    tasks += [
        {"task_id": f"section-{n:02d}", "kind": "section_synthesis", "section": n}
        for n in section_numbers
    ]
    tasks.append({"task_id": "executive", "kind": "executive_synthesis"})
    omitted = {
        "omitted_packets": len(omitted_packets),
        "omitted_packet_ids": [p["packet_id"] for p in omitted_packets],
        "omitted_packet_paths": sorted({p["path"] for p in omitted_packets}),
        "truncated": bool(omitted_packets),
        "total_tasks": len(tasks),
    }
    return tasks, omitted
