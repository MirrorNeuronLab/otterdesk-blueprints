"""Five-candidate scientific ranking and required review qualifications."""
import json
from mn_sdk.agent_events import report_activity
from mn_sdk.blueprint_support.shared_outputs import copy_path_to_host
from mn_sdk_common.publication import ArtifactWrite, publish_bundle

from .configuration import BLUEPRINT_ID, output_directory
from .native_stages import read_discovery_state, write_discovery_state
from .candidates import five_distinct_candidates
from service.scripts.continuous_service import is_fake, simulation_sort_key


def publish_ranking(block, inputs):
    report_activity("Writing the discovery ranking", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    state = read_discovery_state(block, inputs)
    evaluations = state.get("evaluations") or []
    if len(evaluations) != 5:
        raise ValueError("The scientific report requires five evaluated molecules.")
    five_distinct_candidates([row["candidate"] for row in evaluations], synthetic=is_fake(block.config))
    ranked = sorted(evaluations, key=simulation_sort_key)
    artifact = {"schema_version": "mn.blueprint.continuous_discovery_review.v1",
        "created_at": state["service_reports"][0]["completed_at"], "candidate_count": len(ranked),
        "mode": "fake_smoke_test" if is_fake(block.config) else "live",
        "ranked_candidates": ranked, "recommendation": "review_required",
        "review_boundary": "Computational hypotheses only. A human scientific reviewer must assess evidence before laboratory, clinical, regulatory, procurement, or external-system action.",
        "missing_evidence": ["experimental binding and selectivity data", "ADMET and toxicity validation",
                             "reproducible simulation protocol and independent review"],
        "type": "drug_discovery_research_packet", "recommended_action": "review_required",
        "executive_summary": "Prepared five computational candidate evaluations for human scientific review.",
        "confidence": 0.25, "evidence": [{"type": "continuous_discovery_cycle_evaluations",
            "candidate_count": 5, "source_ref": "cycles/cycle-000000/cycle_report.json"}],
        "next_steps": ["Review the ranked computational candidates and source cycle artifacts.",
            "Obtain independent binding, selectivity, ADMET, and toxicity evidence before any downstream action."],
        "source_refs": ["inputs.json", "events.jsonl", "result.json", "service_state.json",
                        "cycle_progress.json", "discovery_service_review.json",
                        *[reference["path"] for reference in state.get("cycle_artifacts", [])]]}
    encoded = json.dumps(artifact, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    receipt = publish_bundle(block.store, [ArtifactWrite(name, path, encoded, kind="json", authoritative=True)
        for name, path in [("review", "discovery_service_review.json"), ("final_artifact", "final_artifact.json"),
                           ("result", "result.json")]], receipt_path=block.root + "/publication.json")
    state["final_report"] = artifact
    state_ref = write_discovery_state(block, state, "ranking")
    output = output_directory(block)
    if output != block.store.run_dir:
        for item in receipt["artifacts"]:
            reference = item["reference"]
            copy_path_to_host(block.store.path(reference["path"]), output / reference["path"])
    web_ui, web_ui_error = {}, ""
    try:
        from .dashboard import publish_static_dashboard
        web_ui = publish_static_dashboard(block)
    except Exception as error:
        web_ui_error = f"Optional result dashboard was not rendered: {type(error).__name__}"
    return {"candidate_count": 5, "state": state_ref, "artifacts": receipt["artifacts"],
            "web_ui": web_ui, "web_ui_error": web_ui_error}
