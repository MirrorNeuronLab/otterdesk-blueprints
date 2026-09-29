"""Catalog contract: bundled report-spec manifest + frozen source snapshot inventory.

Owns loading and validating the 23-section / 150-aspect report specification
library bundled at ``payloads/report_specs`` and the frozen source snapshot
(``snapshot.json`` plus ``evidence/snapshots/<id>/sources.json``).

Polyglot: the source inventory is raw UTF-8 text plus SHA-256.  This module
never imports Python source modules and never executes reviewed source.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

EXPECTED_SECTIONS = 23
EXPECTED_SPECS = 150

_ASPECT_ID = re.compile(r"^AR-(\d{2})-(\d{2})$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-./]*$")
_SAFE_SOURCE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-./]*$")


def bundled_specs_dir(bundle_root=None) -> Path:
    """Resolve the bundled ``payloads/report_specs`` directory."""
    if bundle_root is not None:
        root = Path(bundle_root)
        candidate = (
            root if root.name == "report_specs" else root / "payloads" / "report_specs"
        )
        if (candidate / "manifest.json").exists():
            return candidate
        if (root / "manifest.json").exists():
            return root
        return candidate
    here = Path(__file__).resolve()
    for parent in (here.parent.parent, here.parent.parent.parent):
        candidate = parent / "report_specs"
        if (candidate / "manifest.json").exists():
            return candidate
    return here.parent.parent / "report_specs"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_safe_spec_path(path: str, section_folder: str) -> None:
    if not isinstance(path, str) or not _SAFE_PATH.fullmatch(path):
        raise ValueError(f"Unsafe spec path: {path!r}")
    if path.startswith("/") or ".." in Path(path).parts:
        raise ValueError(f"Unsafe spec path: {path!r}")
    if not path.startswith(section_folder + "/") or not path.endswith("_spec.md"):
        raise ValueError(f"Spec path outside section folder: {path!r}")


def load_catalog(bundle_root=None) -> dict:
    """Load and fully validate the bundled spec library.

    Returns ``{"manifest", "sections", "specs", "conventions"}`` where
    ``specs`` maps aspect ID -> record including full ``text`` and ``sha256``,
    and ``sections`` lists ``{number, title, folder, aspect_ids}`` in order.
    Raises ``ValueError`` on any structural, hash, or safety violation.
    """
    specs_dir = bundled_specs_dir(bundle_root)
    manifest_path = specs_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load report_specs manifest: {exc}") from exc
    sections = manifest.get("sections")
    if not isinstance(sections, list) or len(sections) != EXPECTED_SECTIONS:
        raise ValueError(f"Manifest must define exactly {EXPECTED_SECTIONS} sections")
    try:
        conventions = (specs_dir / "REPORT_CONVENTIONS.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Missing REPORT_CONVENTIONS.md: {exc}") from exc
    if "Applicability and coverage are different" not in conventions:
        raise ValueError(
            "REPORT_CONVENTIONS.md missing applicability/coverage contract"
        )
    specs: dict[str, dict] = {}
    ordered_sections = []
    for entry in sections:
        number = entry.get("number")
        folder = entry.get("folder")
        items = entry.get("specifications")
        if not isinstance(number, int) or not folder or not isinstance(items, list):
            raise ValueError(f"Malformed section entry: {entry!r}")
        if not _SAFE_PATH.fullmatch(folder) or "/" in folder or folder.startswith("."):
            raise ValueError(f"Unsafe section folder: {folder!r}")
        aspect_ids = []
        for item in items:
            aspect_id = item.get("id")
            rel = item.get("path")
            expect = item.get("sha256")
            match = _ASPECT_ID.fullmatch(aspect_id or "")
            if not match or int(match.group(1)) != number:
                raise ValueError(
                    f"Aspect ID {aspect_id!r} does not match section {number}"
                )
            if aspect_id in specs:
                raise ValueError(f"Duplicate aspect ID: {aspect_id}")
            _check_safe_spec_path(rel, folder)
            target = (specs_dir / rel).resolve()
            if not target.is_relative_to(specs_dir.resolve()):
                raise ValueError("Spec path escapes bundled catalog")
            data = target.read_bytes() if target.exists() else None
            if data is None:
                raise ValueError(f"Missing spec file: {rel}")
            actual = _sha256_bytes(data)
            if not isinstance(expect, str) or actual != expect.lower():
                raise ValueError(f"SHA-256 mismatch for {rel}")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Spec file not UTF-8: {rel}") from exc
            if aspect_id not in text:
                raise ValueError(
                    f"Spec file {rel} does not reference its ID {aspect_id}"
                )
            specs[aspect_id] = {
                "id": aspect_id,
                "title": item.get("title", ""),
                "question": item.get("question", ""),
                "section": number,
                "section_folder": folder,
                "path": rel,
                "sha256": actual,
                "text": text,
            }
            aspect_ids.append(aspect_id)
        ordered_sections.append(
            {
                "number": number,
                "title": entry.get("title", ""),
                "folder": folder,
                "aspect_ids": aspect_ids,
            }
        )
    if len(specs) != EXPECTED_SPECS:
        raise ValueError(f"Expected {EXPECTED_SPECS} specs, found {len(specs)}")
    numbers = [s["number"] for s in ordered_sections]
    if numbers != list(range(1, EXPECTED_SECTIONS + 1)):
        raise ValueError(f"Section numbers must be 1..{EXPECTED_SECTIONS}")
    return {
        "manifest": manifest,
        "sections": ordered_sections,
        "specs": specs,
        "conventions": conventions,
        "digest": _sha256_bytes(
            json.dumps(
                {
                    "manifest": manifest,
                    "conventions": _sha256_bytes(conventions.encode()),
                    "specs": {k: v["sha256"] for k, v in sorted(specs.items())},
                },
                sort_keys=True,
            ).encode("utf-8")
        ),
    }


def aspect_section(catalog: dict, aspect_id: str) -> dict:
    """Return the section record owning ``aspect_id`` (``ValueError`` if unknown)."""
    try:
        number = catalog["specs"][aspect_id]["section"]
    except KeyError:
        raise ValueError(f"Unknown aspect ID: {aspect_id}") from None
    for section in catalog["sections"]:
        if section["number"] == number:
            return section
    raise ValueError(f"No section for aspect {aspect_id}")


def _check_safe_source_path(path: str) -> None:
    if (
        not isinstance(path, str)
        or not path
        or "\x00" in path
        or "\\" in path
        or Path(path).is_absolute()
        or any(part in {"..", ".", ""} for part in path.split("/"))
    ):
        raise ValueError(f"Unsafe source path: {path!r}")


def load_snapshot(run_dir, snapshot_override=None) -> dict:
    """Load and validate the frozen source snapshot for a run directory.

    Reads ``snapshot.json`` (a copy of the capture manifest) and
    ``evidence/snapshots/<id>/sources.json`` (``{rel: {sha256, text}}``),
    recomputes every source SHA-256, and cross-checks the manifest source map.
    Returns ``{"snapshot_id", "sources", "inventory", "manifest"}`` where
    ``sources`` maps path -> ``{sha256, text}`` and ``inventory`` is the sorted
    path list.  Raises ``ValueError`` on any missing file, hash mismatch, or
    unsafe path.
    """
    root = Path(run_dir)
    try:
        manifest = json.loads((root / "snapshot.json").read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load snapshot.json: {exc}") from exc
    snapshot_id = snapshot_override or manifest.get("id")
    if not snapshot_id or not re.fullmatch(r"[A-Za-z0-9_\-]+", str(snapshot_id)):
        raise ValueError("snapshot.json has no usable snapshot id")
    sources_path = root / "evidence" / "snapshots" / str(snapshot_id) / "sources.json"
    try:
        raw_sources = json.loads(sources_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load {sources_path}: {exc}") from exc
    if not isinstance(raw_sources, dict) or not raw_sources:
        raise ValueError("sources.json must be a nonempty object")
    declared = manifest.get("sources", {})
    if set(raw_sources) != set(declared):
        raise ValueError("Source inventory differs from snapshot manifest")
    sources: dict[str, dict] = {}
    for rel, record in raw_sources.items():
        _check_safe_source_path(rel)
        if (
            not isinstance(record, dict)
            or "text" not in record
            or "sha256" not in record
        ):
            raise ValueError(f"Malformed source record: {rel}")
        text = record["text"]
        if not isinstance(text, str):
            raise ValueError(f"Source text must be str: {rel}")
        actual = _sha256_bytes(text.encode("utf-8"))
        if actual != str(record["sha256"]).lower():
            raise ValueError(f"Source hash mismatch: {rel}")
        if rel in declared and str(declared[rel]).lower() != actual:
            raise ValueError(f"Source hash disagrees with snapshot manifest: {rel}")
        sources[rel] = {"sha256": actual, "text": text}
    for rel in declared:
        if rel not in sources:
            raise ValueError(f"Manifest source missing from sources.json: {rel}")
    return {
        "snapshot_id": str(snapshot_id),
        "sources": sources,
        "inventory": sorted(sources),
        "manifest": manifest,
    }
