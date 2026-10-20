"""Bind the bounded investigation block to the advisor's existing review policy."""

from mn_sdk_common.committed_artifacts import CommittedArtifactRef, CommittedJsonStore

from . import catalog_planning
from .catalog_store import CatalogStore


def _context(block, inputs):
    return {"run_dir": block.store.run_dir, "config": block.config,
            "payload": inputs, "job_id": block.job_id, "run_id": block.run_id}


def verified_reference(store, reference, *, expected_path):
    """Promote an existing domain digest without accepting a different file."""
    if not isinstance(reference, dict) or reference.get("path") != expected_path:
        raise ValueError("Investigation artifact differs from the expected catalog path")
    result = CommittedArtifactRef(type="artifact_ref", version="mn.committed_json/v1",
        kind="json", path=expected_path, sha256=reference["sha256"],
        size_bytes=store.path(expected_path).stat().st_size)
    store.validate(result)
    return result.to_dict()


def initialize(block, inputs):
    result, _ = catalog_planning.initializer(_context(block, inputs))
    return {**result, "context": verified_reference(block.store, result["context"],
        expected_path="catalog/context.json")}


def plan(block, inputs):
    reference = inputs["seed"]["context"]
    verified_reference(block.store, reference, expected_path="catalog/context.json")
    decision = catalog_planning.planner(_context(block, {}),
        {"context": reference, "_child": inputs["_child"]})["child_plan"]
    if decision["decision"] == "stop":
        return {"done": True, "tasks": [], "rationale": decision["reason"]}
    # Core merges mapped parent ports into every child. `seed` carries the
    # immutable block initialization; the sandbox retains its domain `context`.
    return {"done": False, "tasks": [
        {**task, "input": {**task["input"], "context": reference}}
        for task in decision["steps"]], "rationale": decision["rationale"],
        "evidence_refs": decision.get("evidence_refs", [])}


def summarize(block, inputs):
    work = inputs["input"]
    store = CatalogStore(block.store.run_dir)
    decision = store.read(
        f"catalog/plans/decision-{work['_child']['revision']:02d}.json")
    if decision["context"] != work["seed"]["context"]:
        raise ValueError("Investigation decision belongs to a different context")
    stopped = decision["plan"]["child_plan"]
    if stopped["decision"] != "stop":
        raise ValueError("Investigation summary requires a terminal domain decision")
    output = stopped["output"]
    return {**output, "catalog": verified_reference(block.store, output["catalog"],
        expected_path="catalog/terminal.json")}


def publish(context, *, step_input, llm_client=None):
    from .catalog_publication import publish as publish_catalog

    store = CommittedJsonStore(context["run_dir"])
    summary = store.read(step_input["previous"]["result"])
    if summary["status"] not in {"partial", "review_draft"}:
        raise ValueError("Investigation summary has an invalid terminal status")
    verified_reference(store, summary["catalog"], expected_path="catalog/terminal.json")
    return publish_catalog(context, llm_client=llm_client)
