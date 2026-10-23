"""Source-selection policy, coverage accounting, and immutable review inventory."""

from mn_sdk.agent_events import activity_operation

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from mn_sdk.integrations.block_inputs import capture_declared_inputs
from .ingestion.corpus import CaseCorpus
from .sample_data import prepare_emc2, EMC2_DOCUMENTATION, attribution


@activity_operation('Examining case documents', completed='Examining case documents: completed')
def prepare_sources(context, inputs):
    from .state import capture, capture_result, json_reference, read_capture
    run_dir = context.store.run_dir
    payload = capture_declared_inputs(context, inputs, runtime_file=__file__)
    llm_client = context.resources.get("llm")
    if context.store.path("case/capture.json").exists():
        ref = json_reference(context, "case/capture.json", kind="block_checkpoint")
        if read_capture(context, ref)["request"] != payload:
            raise ValueError("Case source selection changed")
        return capture_result(context, ref)
    from .matter_intake import prepare as prepare_matter
    from .model_preflight import check as check_model
    from .review_scope import limits
    matter = prepare_matter(context, payload)
    review_plan = limits(context.config)
    (run_dir / "case/review_plan.json").write_text(json.dumps(review_plan, indent=2))
    check_model(context, llm_client)
    folder = payload.get("input_folder")
    # The desktop setup form submits an empty optional path as an empty string.
    # It has the same meaning as omitting the field: use the public sample.
    if isinstance(folder, str) and not folder.strip():
        folder = None
    source = (
        Path(folder).expanduser().resolve()
        if folder is not None
        else prepare_emc2(run_dir / "sample/emc2")
    )
    if not source.is_dir():
        raise ValueError(f"input_folder is not an existing directory: {source}")
    if source == run_dir or source in run_dir.parents:
        raise ValueError(
            "run output must be outside input_folder to avoid indexing generated evidence"
        )
    policy = context.config["investigation"]
    corpus = CaseCorpus(source, access_scope=policy["access_scope"],
                        excluded_paths=EMC2_DOCUMENTATION if folder is None else ())
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
        context.check()
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("source changed before original snapshot was frozen")
        (originals / expected).write_bytes(content)
    from .handling import review_flags
    from .matter_intake import digest as matter_digest
    from .financial_review import build as reconcile
    flags = review_flags(documents, matter["exclusions"])
    (case / "handling.json").write_text(json.dumps({"flags": flags, "reviewed_exclusions": matter["exclusions"],
        "qualification": "Conservative handling decisions, not legal privilege determinations. Original audit retention is not a cleared sharing package."}, indent=2))
    # Validate every user-supplied quotation before any case-model call.
    reconcile(matter, documents, flags)
    records = [asdict(d) for d in documents]
    # Exact normalized text is durable and authoritative for cited character spans.
    corpus_path = case / "sources.json"
    corpus_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    inventory = {
        "source_root": str(source),
        "matter_sha256": matter_digest(run_dir),
        "handling_sha256": hashlib.sha256((case / "handling.json").read_bytes()).hexdigest(),
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
        "attachment_processing": corpus.processing_gaps,
        "archives_not_extracted": [p.relative_to(source).as_posix() for p in paths if p.suffix.casefold() == '.zip'],
        "duplicate_source_groups": [sorted(d.source_id for d in documents if d.content_sha256 == digest)
            for digest in sorted({d.content_sha256 for d in documents})
            if sum(d.content_sha256 == digest for d in documents) > 1],
    }
    if folder is None and (source / 'LICENSE.md').is_file():
        inventory['sample_attribution'] = attribution(source)
        (run_dir / 'sample_attribution.json').write_text(json.dumps(inventory['sample_attribution'], indent=2))
    from .file_identity import capture_file_identities
    inventory['repository_id'], inventory['file_identities'] = capture_file_identities(
        source, run_dir, context, original_hashes)
    (case / "source_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )
    from .source_query import publish
    publish(context, documents, {
        'job_id': context.job_id or os.environ.get('MN_JOB_ID'),
        'run_id': context.run_id or os.environ.get('MN_WORKFLOW_RUN_ID') or os.environ.get('MN_RUN_ID'),
    })
    return capture_result(context, capture(context, payload))


def verified(context, result):
    from .state import read_capture
    read_capture(context, result["evidence"])
    return True


class PreparedCorpus:
    """Read the frozen source snapshot instead of rescanning mutable user files."""

    def __init__(self, case_dir, access_scope):
        from .models import CaseDocument

        case_dir = Path(case_dir)
        content = (case_dir / "sources.json").read_bytes()
        inventory = json.loads((case_dir / "source_inventory.json").read_text())
        if hashlib.sha256(content).hexdigest() != inventory["sources_sha256"]:
            raise ValueError("prepared source snapshot hash mismatch")
        for name, key in (("matter.json", "matter_sha256"), ("handling.json", "handling_sha256")):
            if key in inventory and hashlib.sha256((case_dir / name).read_bytes()).hexdigest() != inventory[key]:
                raise ValueError("prepared matter handling binding changed")
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
