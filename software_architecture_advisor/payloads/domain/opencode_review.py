"""One bounded OpenCode review invocation; durable attempts and verified results."""

import json
import time
from pathlib import Path
from mn_opencode_skill import OpenCodeRequest, OpenCodeError, run_opencode
from .catalog_store import CatalogStore, fingerprint
from .catalog_planning import catalog_settings
from .opencode_models import provider_config
from .catalog_contract import load_catalog, load_snapshot
from .review_packets import chunk_snapshot
from .review_prompts import build_prompt, expand_evidence
from .review_response import validate_result
from .retry_budget import effective_config, effective_deadline


def _blocked(task, reason, status="blocked"):
    return {
        "task_id": task["task_id"],
        "kind": task["kind"],
        "status": status,
        "reason": reason,
        "claims": [],
        "observations": [],
        "proposed_followups": [],
    }


def handle_task(context, work, *, llm_client=None):
    review, opener = catalog_settings(context["config"])
    store = CatalogStore(context["run_dir"])
    saved = store.load_ref(work["context"])
    plan = store.load_ref(saved["plan"])
    task = store.load_ref(work["task"])
    if review != saved["request"]["review"] or opener != saved["request"]["opencode"]:
        raise ValueError("Frozen configuration changed")
    review, opener = catalog_settings(effective_config(context["config"]))
    deadline = effective_deadline(saved["deadline"], review["walltime_seconds"])
    catalog = load_catalog()
    snapshot = load_snapshot(context["run_dir"])
    if (
        catalog["digest"] != plan["catalog_digest"]
        or fingerprint(snapshot["manifest"]) != saved["request"]["snapshot"]
    ):
        raise ValueError("Frozen snapshot or report catalog changed")
    if task.get("snapshot_id") != snapshot["snapshot_id"]:
        raise ValueError("Task snapshot differs")
    task_id = task["task_id"]
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id):
        raise ValueError("Unsafe task id")
    request_path = f"catalog/requests/{task_id}.json"
    identity = fingerprint({"task": task, "settings": saved["request"]})
    result = store.result(task_id)
    if result is not None:
        if result["identity"] != identity:
            raise ValueError("Inconsistent task replay")
        return {
            "task_id": task_id,
            "result": store.read(f"catalog/receipts/{task_id}.json"),
            "status": result["status"],
        }
    packets = {
        p["packet_id"]: p for p in chunk_snapshot(snapshot, review["chunk_bytes"])
    }
    if store.path(request_path).exists():
        request = store.read(request_path)
        if request["identity"] != identity:
            raise ValueError("Inconsistent request replay")
    else:
        prepared = build_prompt(
            task,
            catalog,
            snapshot,
            packets,
            store.results(),
            review["prompt_bytes"],
            plan["omitted"],
            quality_config=saved['request'].get('retrieval_config', {}),
        )
        request = {"identity": identity, **prepared}
        store.write(request_path, request)
    request_hash = fingerprint(request)
    if review["offline"]:
        value = _blocked(
            task,
            "Explicit offline mode: no model call; no architecture conclusion.",
            "not_analyzed",
        )
    elif request.get('context_quality',{}).get('action')=='insufficient_evidence':
        value = _blocked(task, 'Required source evidence is unavailable: ' +
                         ', '.join(request['context_quality']['reasons']))
    elif time.time() >= deadline:
        value = _blocked(task, "Review deadline reached before dispatch")
    else:
        reservation = store.reserve(task_id, request_hash, review["max_calls"])
        if reservation != "reserved":
            value = _blocked(
                task,
                "Previous attempt has no committed result; automatic retry is disabled"
                if reservation == "interrupted"
                else "OpenCode call budget exhausted",
            )
        else:
            started = time.monotonic()
            try:
                if llm_client is None:
                    if b"openshell-sandbox" not in Path("/proc/1/cmdline").read_bytes():
                        raise RuntimeError("Live review requires an OpenShell sandbox")
                    folder = (
                        Path(opener["sandbox_root"])
                        / "catalog-tasks"
                        / fingerprint(saved["request"])[:20]
                        / task_id
                    )
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / "review-input.json").write_text(request["prompt"])
                    provider_path = folder / "provider-config.json"
                    provider_path.write_text(json.dumps(provider_config(opener)))
                    response = run_opencode(
                        OpenCodeRequest(
                            folder=str(folder),
                            mode="review",
                            prompt=request["prompt"],
                            model=opener["model"],
                            sandbox_root=opener["sandbox_root"],
                            timeout_seconds=max(
                                1,
                                min(
                                    opener["timeout_seconds"],
                                    int(deadline - time.time()),
                                ),
                            ),
                            max_output_bytes=opener["max_output_bytes"],
                        ),
                        env={"OPENCODE_CONFIG": str(provider_path)},
                    )
                    raw = response.text
                else:
                    raw = llm_client(request["prompt"])
                if not isinstance(raw, str) or len(raw.encode()) > 200000:
                    raise ValueError("Response size exceeded")
                value = expand_evidence(json.loads(raw), request["evidence"])
                value = validate_result(
                    {**task, "input_task_ids": request["input_task_ids"]},
                    value,
                    snapshot,
                    packets,
                    request["requirements"],
                    list(request["evidence"].values()),
                )
                value["input_omissions"] = request["omissions"]
                value["input_task_ids"] = request["input_task_ids"]
                if value.get("coverage") == "complete_for_stated_scope" and any(
                    request["omissions"][k]
                    for k in ["source_packets", "prior_results", "evidence_spans"]
                ):
                    value["coverage"] = "partial"
                    value.setdefault("limitations", []).append(
                        "Evidence inputs were bounded; review does not establish full project coverage."
                    )
            except Exception as exc:
                # Preserve class, not provider/source payloads which can contain credentials.
                value = _blocked(
                    task,
                    str(exc)
                    if isinstance(exc, OpenCodeError)
                    else f"{type(exc).__name__}: structured evidence validation failed; inspect the task contract and retry explicitly in a new run.",
                )
            value["elapsed_seconds"] = round(time.monotonic() - started, 3)
    value.update(identity=identity, request_hash=request_hash, model=opener["model"])
    ref = store.finish(task_id, value)
    return {"task_id": task_id, "status": value["status"], "result": ref}
