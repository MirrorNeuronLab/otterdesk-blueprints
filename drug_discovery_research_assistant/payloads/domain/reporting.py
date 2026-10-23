"""Five-candidate scientific ranking and required review qualifications."""
import json
from mn_sdk.agent_events import report_activity
from mn_sdk_common.publication import ArtifactWrite
from mn_sdk.integrations.block_publication_files import publish_artifact_bundle, publish_files, merge_publications

from .configuration import BLUEPRINT_ID
from .native_stages import read_discovery_state, write_discovery_state
from .candidates import five_distinct_candidates
from service.scripts.continuous_service import is_fake, simulation_sort_key


def _scientific_output_writes(block):
    """Declare the discovery archive for transport out of the scientific worker."""
    paths = {path.relative_to(block.store.run_dir).as_posix()
             for path in block.store.path("cycles").rglob("*") if path.is_file()}
    paths.update(name for name in ("service_state.json", "cycle_progress.json",
        "leading_candidate.json", "leading_candidate.svg") if block.store.path(name).is_file())
    return [ArtifactWrite(name, name, block.store.path(name).read_bytes(),
        required=not name.endswith((".svg", ".png"))) for name in sorted(paths)]


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
    writes = [ArtifactWrite(name, path, encoded, kind="json", authoritative=True)
        for name, path in [("review", "discovery_service_review.json"), ("final_artifact", "final_artifact.json"),
                           ("result", "result.json")]]
    receipt = publish_artifact_bundle(block, writes, receipt_path=block.root + "/publication.json")
    published_files = publish_files(block, [*writes, *_scientific_output_writes(block)], name="scientific-review")
    state["final_report"] = artifact
    state_ref = write_discovery_state(block, state, "ranking")
    web_ui, web_ui_error = {}, ""
    try:
        from .dashboard import publish_static_dashboard
        web_ui = publish_static_dashboard(block)
        dashboard_receipt = block.store.read_path("web/publication.json")
        optional_writes = [ArtifactWrite(item["id"], item["reference"]["path"],
            block.store.read_bytes(item["reference"]), kind=item["reference"]["kind"], required=False)
            for item in dashboard_receipt["artifacts"]]
        published_files = merge_publications(block, published_files,
            publish_files(block, optional_writes, name="review-previews"))
    except Exception as error:
        web_ui_error = f"Optional result dashboard was not rendered: {type(error).__name__}"
    return {"candidate_count": 5, "state": state_ref, "artifacts": receipt["artifacts"],
            "web_ui": web_ui, "web_ui_error": web_ui_error, "published_files": published_files}
