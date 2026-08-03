from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support.workflow_state import write_json

from .collaboration import build_packet, peer_signals, persist_packet, write_final_artifact
from .inputs import json_object, resolve_input_file, source_descriptor


DRAFT_PACKAGES_PATH = "draft_content_packages.json"


def run_content_studio_director(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "plan_content_batch":
        return _plan_content_batch(context)
    if step_id == "publish_content_studio_packet":
        return _publish_content_packet(context)
    raise ValueError(f"Content Studio co-worker does not own step {step_id!r}")


def _dataset(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    path = resolve_input_file(context, "learning_briefs_file", "approved_learning_briefs.json")
    payload = json_object(path)
    briefs = [item for item in payload.get("briefs") or [] if isinstance(item, dict)]
    synthetic = str(payload.get("data_status") or "").lower() == "synthetic_demo"
    return briefs, source_descriptor(path, synthetic=synthetic), synthetic


def _plan_content_batch(context: dict[str, Any]) -> dict[str, Any]:
    briefs, source, synthetic = _dataset(context)
    accepted = [brief for brief in briefs if str(brief.get("learning_review_status") or "").upper() in {"PASS", "PASS WITH CONDITIONS"}]
    rejected = [brief for brief in briefs if brief not in accepted]
    packages = [_draft_package(brief) for brief in accepted]
    artifact = {
        "schema_version": "mn.bibblio.draft_content_batch.v1",
        "classification": "draft_child_facing_content",
        "publication_authorized": False,
        "packages": packages,
        "rejected_brief_ids": [str(item.get("brief_id") or item.get("id") or "unknown") for item in rejected],
    }
    write_json(Path(context["run_dir"]) / DRAFT_PACKAGES_PATH, artifact)
    peers = peer_signals(context)
    packet = build_packet(
        context,
        stage="plan_content_batch",
        objective="Convert only learning-approved briefs into a small, reusable, cost-bounded draft content batch.",
        trigger="Approved learning briefs enter the Content Studio queue.",
        sources=[source],
        observed_facts=[
            f"The supplied file contains {len(briefs)} briefs; {len(accepted)} have an accepted learning-review status.",
            f"The draft batch contains {len(packages)} versioned packages and rejects {len(rejected)} incomplete or unapproved briefs.",
        ],
        assumptions=["A learning-approved brief is not a publication approval and does not replace complete package review."],
        analysis={
            "draft_package_count": len(packages),
            "rejected_brief_count": len(rejected),
            "draft_packages_artifact": DRAFT_PACKAGES_PATH,
            "peer_goal_packet_count": len(peers["signals"]),
            "peer_goal_signals": peers["signals"],
            "production_pattern": "small reusable story-and-activity batch",
        },
        recommendation="Produce the smallest complete draft batch, reuse approved structures, and send every package back to Learning Science and Safety before release.",
        confidence="low" if synthetic else "medium",
        risks=["Draft generation can introduce factual, answer-key, visual, audio, licensing, or personalization defects.", "Content volume can increase cost without improving retained value."],
        requested_approval=["Learning Science, child safety, brand, licensing, accessibility, and founder reviewers approve each complete package before publication."],
        outputs=["draft content batch", "production QA checklist", "review submission queue"],
        next_check="After complete package review and parent usability evidence.",
    )
    return {**persist_packet(context, packet), "draft_packages_artifact": DRAFT_PACKAGES_PATH}


def _publish_content_packet(context: dict[str, Any]) -> dict[str, Any]:
    artifact = json_object(Path(context["run_dir"]) / DRAFT_PACKAGES_PATH)
    packages = artifact.get("packages") if isinstance(artifact.get("packages"), list) else []
    packet = build_packet(
        context,
        stage="publish_content_studio_packet",
        objective="Publish a production-status packet and review bundle without releasing content to children.",
        trigger="Draft assembly and deterministic production checks are complete.",
        sources=[{"source_ref": "artifact:draft_content_packages.json", "data_quality_note": "Draft content requires complete downstream review."}],
        observed_facts=[f"{len(packages)} draft packages are ready for mandatory learning, safety, and human review."],
        assumptions=["No package is live, parent-approved, or evidence of learning efficacy."],
        analysis={"draft_package_count": len(packages), "draft_packages_artifact": DRAFT_PACKAGES_PATH, "publication_authorized": False},
        recommendation="Review and revise the complete packages; release none until Learning Science returns an approved decision and the founder authorizes publication.",
        confidence="low",
        risks=["Partial review can miss cross-modal defects.", "Synthetic briefs do not establish parent demand."],
        requested_approval=["Qualified reviewers and the founder approve each release candidate."],
        outputs=["Content Studio production packet", "mandatory review bundle"],
        next_check="When review decisions and revision requirements return.",
        publication_state="final",
    )
    persisted = persist_packet(context, packet)
    final = write_final_artifact(
        context,
        packet,
        artifact_type="bibblio_content_studio_production_packet",
        executive_summary="The Content Studio independently converted approved briefs into versioned draft package structures and stopped at the mandatory learning-safety and founder review boundary.",
        evidence={"draft_package_count": len(packages), "draft_packages_artifact": DRAFT_PACKAGES_PATH, "publication_authorized": False},
        next_steps=[
            "Send complete draft packages to the Learning Science and Safety co-worker.",
            "Apply every required revision and rerun production QA.",
            "Track generation cost, provenance, accessibility, and reusable component coverage.",
            "Publish only after explicit human approval.",
        ],
        data_status=str(artifact.get("classification") or "unknown"),
    )
    return {**persisted, **final}


def _draft_package(brief: dict[str, Any]) -> dict[str, Any]:
    brief_id = str(brief.get("brief_id") or brief.get("id") or "unknown")
    skill = str(brief.get("skill_id") or "unmapped-skill")
    return {
        "content_id": f"draft-{brief_id}",
        "version": 1,
        "brief_id": brief_id,
        "age_band": str(brief.get("age_band") or "not_reported"),
        "skill_id": skill,
        "learning_objective": str(brief.get("learning_objective") or ""),
        "production_status": "draft_review_required",
        "story_architecture": [
            "Model the target skill in a short parent-child story context.",
            "Provide guided practice with supportive feedback.",
            "Offer one independent attempt and a clear ending.",
        ],
        "activity_contract": {
            "practice_opportunities": int(brief.get("practice_opportunities") or 3),
            "answer_key_status": "must_be_independently_validated",
            "parent_coplay_guidance_required": True,
        },
        "personalization": {
            "allowed_fields": list(brief.get("approved_personalization_fields") or []),
            "minimum_data_only": True,
        },
        "required_reviews": ["learning_science", "child_safety", "brand", "accessibility", "founder_publish_approval"],
    }
