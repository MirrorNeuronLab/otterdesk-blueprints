"""Source-selection policy, coverage accounting, and immutable review inventory."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from mn_sdk.step_runtime import artifact_reference
from .ingestion.corpus import CaseCorpus
from .sample_data import prepare_emc2


def prepare_sources(context, *, llm_client=None):
    run_dir = Path(context["run_dir"])
    payload = context["payload"]
    folder = payload.get("input_folder")
    source = (
        Path(folder).expanduser().resolve()
        if folder is not None
        else prepare_emc2(run_dir / "sample/emc2")
    )
    if folder is not None and not str(folder).strip():
        raise ValueError("input_folder must not be blank when supplied")
    if not source.is_dir():
        raise ValueError(f"input_folder is not an existing directory: {source}")
    if source == run_dir or source in run_dir.parents:
        raise ValueError(
            "run output must be outside input_folder to avoid indexing generated evidence"
        )
    policy = context["config"]["investigation"]
    corpus = CaseCorpus(source, access_scope=policy["access_scope"])
    paths = list(corpus._source_paths())
    if not paths or len(paths) > policy["max_files"]:
        raise ValueError("input folder is empty or exceeds max_files")
    sizes = [p.stat().st_size for p in paths]
    if max(sizes) > policy["max_file_bytes"] or sum(sizes) > policy["max_total_bytes"]:
        raise ValueError("input folder exceeds configured source byte limits")
    original_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    documents = corpus.scan()
    if any(
        hashlib.sha256(p.read_bytes()).hexdigest() != original_hashes[p] for p in paths
    ):
        raise ValueError(
            "source files changed during evidence preparation; retry with a stable input folder"
        )
    if not any(d.text and d.text.strip() for d in documents):
        raise ValueError(
            "input folder contains no readable text; inspect document formats or provide extracted text"
        )
    case = run_dir / "case"
    case.mkdir(parents=True, exist_ok=True)
    originals = case / "originals"
    originals.mkdir(exist_ok=True)
    for path, expected in original_hashes.items():
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("source changed before original snapshot was frozen")
        (originals / expected).write_bytes(content)
    records = [asdict(d) for d in documents]
    # Exact normalized text is durable and authoritative for cited character spans.
    corpus_path = case / "sources.json"
    corpus_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    inventory = {
        "source_root": str(source),
        "sample": folder is None,
        "document_count": len(records),
        "readable_count": sum(d.text is not None for d in documents),
        "sources_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "files": [
            {
                "path": p.relative_to(source).as_posix(),
                "sha256": original_hashes[p],
                "size_bytes": p.stat().st_size,
            }
            for p in paths
        ],
        "sources": [{k: v for k, v in r.items() if k != "text"} for r in records],
        "unreadable_sources": [d.source_id for d in documents if d.text is None],
    }
    (case / "source_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )
    refs = [
        artifact_reference("source_inventory", "case/source_inventory.json"),
        artifact_reference("normalized_sources", "case/sources.json"),
        artifact_reference("original_sources", "case/originals"),
    ]
    return {
        "source_inventory": refs[0],
        "document_count": len(records),
        "unreadable_count": len(inventory["unreadable_sources"]),
    }, refs


class PreparedCorpus:
    """Read the frozen source snapshot instead of rescanning mutable user files."""

    def __init__(self, case_dir, access_scope):
        from .models import CaseDocument

        case_dir = Path(case_dir)
        content = (case_dir / "sources.json").read_bytes()
        inventory = json.loads((case_dir / "source_inventory.json").read_text())
        if hashlib.sha256(content).hexdigest() != inventory["sources_sha256"]:
            raise ValueError("prepared source snapshot hash mismatch")
        self.root = Path(inventory["source_root"])
        self.access_scope = access_scope
        self.documents = tuple(CaseDocument(**r) for r in json.loads(content))
        if any(d.access_scope != access_scope for d in self.documents):
            raise ValueError("prepared source scope mismatch")

    def scan(self):
        return self.documents

    def inject(self, index):
        return tuple(
            index.inject_bytes(d.text.encode("utf-8"), d.source_id, d.access_scope)
            for d in self.documents
            if d.text is not None
        )
