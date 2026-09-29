"""Domain policy for hundreds of Core-managed bounded architecture tasks."""

import math
import time
from mn_sdk.child_workflow import round_plan, stop_plan
from mn_sdk.step_runtime import artifact_reference
from mn_opencode_skill import DEFAULT_MODEL
from .opencode_models import SPARK_BASE_URL, normalize_model, validate_spark_url
from .catalog_store import CatalogStore, fingerprint
from .catalog_contract import load_catalog, load_snapshot
from .review_packets import chunk_snapshot, build_full_task_list

DEFAULTS = {
    "max_tasks": 1024,
    "max_rounds": 20,
    "tasks_per_round": 64,
    "chunk_bytes": 24000,
    "prompt_bytes": 60000,
    "max_calls": 1024,
    "walltime_seconds": 86400,
    "max_followups": 64,
}
OPEN_DEFAULTS = {
    "model": DEFAULT_MODEL,
    "spark_base_url": SPARK_BASE_URL,
    "timeout_seconds": 600,
    "max_output_bytes": 1048576,
    "sandbox_root": "/sandbox/job",
}
ORDER = {
    "source_scan": 0,
    "aspect_analysis": 1,
    "aspect_challenge": 2,
    "evidence_followup": 3,
    "section_synthesis": 4,
    "executive_synthesis": 5,
}


def catalog_settings(config):
    review = {**DEFAULTS, **config.get("catalog_review", {})}
    opener = {**OPEN_DEFAULTS, **config.get("opencode", {})}
    limits = {
        "max_tasks": (325, 1024),
        "max_rounds": (1, 20),
        "tasks_per_round": (1, 64),
        "chunk_bytes": (1024, 24000),
        "prompt_bytes": (24000, 100000),
        "max_calls": (1, 1024),
        "walltime_seconds": (1, 86400),
        "max_followups": (0, 64),
    }
    for key, (low, high) in limits.items():
        if type(review[key]) is not int or not low <= review[key] <= high:
            raise ValueError(f"catalog_review.{key} must be {low}..{high}")
    review["offline"] = config.get("offline", False)
    if type(review["offline"]) is not bool:
        raise ValueError("offline must be boolean")
    opener["model"] = normalize_model(opener["model"])
    opener["spark_base_url"] = validate_spark_url(opener["spark_base_url"])
    for key, upper in [("timeout_seconds", 600), ("max_output_bytes", 8388608)]:
        if type(opener[key]) is not int or not 1 <= opener[key] <= upper:
            raise ValueError(f"opencode.{key} must be 1..{upper}")
    if opener["sandbox_root"] != "/sandbox/job":
        raise ValueError("The declared OpenShell worker requires /sandbox/job")
    return review, opener


def initializer(context, *, llm_client=None):
    review, opener = catalog_settings(context["config"])
    store = CatalogStore(context["run_dir"])
    catalog, snapshot = load_catalog(), load_snapshot(context["run_dir"])
    request = {
        "review": review,
        "opencode": opener,
        "catalog": catalog["digest"],
        "snapshot": fingerprint(snapshot["manifest"]),
        "goal": context["payload"].get("goal", ""),
    }
    if store.path("catalog/context.json").exists():
        saved = store.read("catalog/context.json")
        if saved["request_hash"] != fingerprint(request):
            raise ValueError("Initialization inputs changed")
        ref = store.write("catalog/context.json", saved)
        return {"context": ref, "status": "planning"}, [
            artifact_reference("catalog_context", ref["path"])
        ]
    packets = chunk_snapshot(snapshot, review["chunk_bytes"])
    # Reserve catalog/report tasks and up to two rounds of dynamic investigation.
    fixed = 2 * len(catalog["specs"]) + len(catalog["sections"]) + 1
    remaining_rounds = (
        review["max_rounds"]
        - 2 * math.ceil(len(catalog["specs"]) / review["tasks_per_round"])
        - 2
    )
    followup_rounds = (
        min(2, max(0, remaining_rounds - 1)) if review["max_followups"] else 0
    )
    scan_capacity = max(
        1, (remaining_rounds - followup_rounds) * review["tasks_per_round"]
    )
    task_cap = min(review["max_tasks"] - review["max_followups"], fixed + scan_capacity)
    tasks, omitted = build_full_task_list(catalog, packets, max(fixed + 1, task_cap))
    task_refs = {}
    for task in tasks:
        full = {**task, "snapshot_id": snapshot["snapshot_id"]}
        task_refs[task["task_id"]] = store.write(
            f"catalog/tasks/{task['task_id']}.json", full
        )
    plan = {
        "snapshot_id": snapshot["snapshot_id"],
        "catalog_digest": catalog["digest"],
        "tasks": tasks,
        "task_refs": task_refs,
        "packet_index": [{k: v for k, v in p.items() if k != "text"} for p in packets],
        "omitted": omitted,
    }
    plan_ref = store.write("catalog/plan.json", plan)
    value = {
        "request_hash": fingerprint(request),
        "request": request,
        "plan": plan_ref,
        "started": time.time(),
        "deadline": time.time() + review["walltime_seconds"],
    }
    ref = store.write("catalog/context.json", value)
    return {"context": ref, "status": "planning", "planned_tasks": len(tasks)}, [
        artifact_reference("catalog_context", ref["path"]),
        artifact_reference("catalog_plan", plan_ref["path"]),
    ]


def _followups(store, tasks, results, packets, limit):
    existing = [t for t in tasks if t["kind"] == "evidence_followup"]
    accepted = []
    seen = {(t["packet_id"], t["reason"].strip().lower()) for t in existing}
    rejected = []
    for task in tasks:
        if task["kind"] not in {
            "source_scan",
            "aspect_analysis",
            "aspect_challenge",
            "evidence_followup",
        }:
            continue
        value = results.get(task["task_id"], {})
        if value.get("status") != "completed":
            continue
        allowed_refs = {
            o.get("observation_id") for o in value.get("observations", [])
        } | {c["claim_id"] for c in value.get("claims", [])}
        for proposal in value.get("proposed_followups", []):
            key = (proposal["packet_id"], proposal["reason"].strip().lower())
            if key in seen:
                continue
            depth = task.get("depth", 0) + 1
            if (
                depth > 2
                or len(existing) + len(accepted) >= limit
                or not set(proposal["evidence_refs"]) <= allowed_refs
                or proposal["packet_id"] not in packets
            ):
                rejected.append(
                    {
                        "parent": task["task_id"],
                        "reason": "followup budget, depth, or evidence constraint",
                    }
                )
                continue
            seen.add(key)
            item = {
                **proposal,
                "parent_task": task["task_id"],
                "depth": depth,
                "kind": "evidence_followup",
                "snapshot_id": task.get("snapshot_id"),
                "aspect_id": task.get("aspect_id"),
            }
            item["task_id"] = "followup-" + fingerprint(item)[:20]
            accepted.append(item)
    return accepted, rejected


def planner(context, work, *, llm_client=None):
    store = CatalogStore(context["run_dir"])
    saved = store.load_ref(work["context"])
    plan = store.load_ref(saved["plan"])
    review, opener = catalog_settings(context["config"])
    if saved["request"]["review"] != review or saved["request"]["opencode"] != opener:
        raise ValueError("Review configuration changed after initialization")
    revision = work["_child"]["revision"]
    if type(revision) is not int or revision < 0:
        raise ValueError("Invalid child revision")
    cache = f"catalog/plans/decision-{revision:02d}.json"
    if store.path(cache).exists():
        return store.read(cache)["plan"]
    from .review_admission import reconcile
    reconcile(store)
    results = store.results()
    tasks = [store.load_ref(r) for r in plan["task_refs"].values()]
    admitted = set()
    for r in range(revision):
        prior = store.read(f"catalog/plans/decision-{r:02d}.json")
        if prior["plan"]["child_plan"]["decision"] != "execute":
            raise ValueError("Cannot plan after terminal decision")
        for node in prior["plan"]["child_plan"]["steps"]:
            task = store.load_ref(node["input"]["task"])
            admitted.add(task["task_id"])
            if task["task_id"] not in results:
                raise ValueError("Prior round has unresolved tasks")
            if all(t["task_id"] != task["task_id"] for t in tasks):
                tasks.append(task)
    extra, rejected = _followups(
        store,
        tasks,
        results,
        {p["packet_id"] for p in plan["packet_index"]},
        review["max_followups"],
    )
    available = max(0, review["max_tasks"] - len(tasks))
    tasks += extra[:available]
    pending = sorted(
        (t for t in tasks if t["task_id"] not in admitted),
        key=lambda t: (ORDER[t["kind"]], t["task_id"]),
    )
    reserved = store.reservations()
    reason = None
    if not pending:
        reason = "All admitted tasks resolved"
    elif time.time() >= saved["deadline"]:
        reason = "Review walltime exhausted"
    elif revision >= review["max_rounds"]:
        reason = "Child round budget exhausted"
    elif store.usage()["catalog_models"] >= review["max_calls"] and not any(t["task_id"] in reserved for t in pending):
        reason = "OpenCode call budget exhausted"
    if reason:
        terminal = {
            "stop_reason": reason,
            "planned_tasks": len(tasks),
            "resolved_tasks": len(results),
            "pending_task_ids": [t["task_id"] for t in pending],
            "rejected_followups": rejected,
            "omitted": plan["omitted"],
            "usage": store.usage(),
        }
        ref = store.write("catalog/terminal.json", terminal)
        result = stop_plan(
            revision=revision,
            reason=reason,
            output={
                "status": "partial"
                if pending or plan["omitted"]["truncated"]
                else "review_draft",
                "catalog": ref,
            },
        )
    else:
        phase = pending[0]["kind"]
        remaining = review["max_calls"] - store.usage()["catalog_models"] + sum(t["task_id"] in reserved for t in pending if t["kind"] == phase)
        batch = [t for t in pending if t["kind"] == phase][: min(review["tasks_per_round"], remaining if not review["offline"] else review["tasks_per_round"])]
        nodes = []
        previous = []
        from .review_admission import admit
        import os
        actual_run_id = os.environ.get("MN_WORKFLOW_RUN_ID") or os.environ.get("MN_RUN_ID")
        for task in batch:
            admitted_input = admit(store, saved, plan, task, review, opener, run_id=actual_run_id)
            if admitted_input is None:
                break
            ref = store.write(f"catalog/tasks/{task['task_id']}.json", task)
            nodes.append(
                {
                    "id": task["task_id"],
                    "template": "review_architecture_packet",
                    "needs": previous,
                    "input": {"task": ref, "review_input": admitted_input},
                }
            )
            previous = [task["task_id"]]
        result = round_plan(
            revision=revision,
            steps=nodes,
            rationale=f"Review {len(nodes)} bounded {phase} tasks",
            evidence_refs=[saved["plan"]],
        )
    store.write(cache, {"context": work["context"], "plan": result})
    return result
