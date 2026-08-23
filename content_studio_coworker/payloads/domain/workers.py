from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support.workflow_state import write_json

from .collaboration import build_packet, persist_packet, write_final_artifact
from .inputs import json_object, normalized_inputs, resolve_input_file, source_descriptor


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
        "schema_version": "mn.content_studio.draft_content_batch.v1",
        "classification": "draft_child_facing_content",
        "publication_authorized": False,
        "packages": packages,
        "rejected_brief_ids": [str(item.get("brief_id") or item.get("id") or "unknown") for item in rejected],
    }
    write_json(Path(context["run_dir"]) / DRAFT_PACKAGES_PATH, artifact)
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
    inputs = normalized_inputs(context)
    business_name = str(inputs["business_name"])
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
        analysis={
            "draft_package_count": len(packages),
            "draft_packages_artifact": DRAFT_PACKAGES_PATH,
            "publication_authorized": False,
        },
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
        artifact_type="content_studio_production_brief",
        executive_summary=f"The Content Studio independently converted {business_name}'s approved briefs into versioned draft package structures and stopped at the mandatory quality, safety, and founder-review boundary.",
        evidence={"draft_package_count": len(packages), "draft_packages_artifact": DRAFT_PACKAGES_PATH, "publication_authorized": False},
        next_steps=[
            "Send complete draft packages to the Learning Science and Safety co-worker.",
            "Apply every required revision and rerun production QA.",
            "Track generation cost, provenance, accessibility, and reusable component coverage.",
            "Publish only after explicit human approval.",
        ],
        data_status=str(artifact.get("classification") or "unknown"),
        role_contribution="Turn approved customer-value briefs into a small, reusable, measurable supply of release candidates without confusing generated drafts with finished product.",
        north_star_question="What is the smallest approved content batch that can test customer value, retention, and repeatable production economics?",
        role_scorecard=[
            {"metric": "draft_packages_ready", "current": len(packages), "target": "smallest batch sufficient for one customer-value test", "decision_use": "Limits inventory and review waste."},
            {"metric": "publication_authorized", "current": False, "target": "true only after complete review and founder approval", "decision_use": "Keeps draft status unambiguous."},
            {"metric": "first_pass_review_rate", "current": "not_measured", "target": "improve without weakening standards", "decision_use": "Finds specification and production defects."},
            {"metric": "cost_per_approved_package", "current": "needs production and Finance evidence", "target": "within Finance-approved unit-cost guardrail", "decision_use": "Connects content supply to viable economics."},
            {"metric": "reusable_component_coverage", "current": "not_measured", "target": "increase where reuse preserves quality", "decision_use": "Improves throughput without unsafe shortcuts."},
        ],
        founder_decisions=[
            {"decision": "Approve the proposed batch size and test purpose", "why_now": "Production should answer a customer-value question, not create speculative inventory."},
            {"decision": "Assign complete-package reviewers", "why_now": "No draft can become customer-facing until all required disciplines review the same version."},
            {"decision": "Approve release, revise, or stop after review", "why_now": "Learning approval at brief intake does not cover defects introduced during production."},
        ],
        cross_functional_handoffs=[
            {"to": "learning_quality_safety_director", "provides": "versioned complete packages, provenance, answer keys, and QA results", "needs_from": "approved briefs, conditions, blocked topics, and final review decisions"},
            {"to": "customer_lifecycle_director", "provides": "approved continuation assets and package metadata", "needs_from": "activation friction, content gaps, retained-use patterns, and customer language"},
            {"to": "growth_partnerships_lead", "provides": "approved demo and proof assets with explicit claim limits", "needs_from": "priority audience, channel format, objections, and proof-asset requirements"},
            {"to": "business_finance_controller", "provides": "production time, revision rate, asset cost, and reuse coverage", "needs_from": "batch budget and approved cost-per-package guardrails"},
        ],
        ninety_day_plan=[
            {"days": "0-30", "outcome": "Produce and completely review the smallest approved batch; record every defect, revision, cost, and reused component."},
            {"days": "31-60", "outcome": "Release only approved packages into one bounded customer-value test and supply relevant assets to Growth and Lifecycle."},
            {"days": "61-90", "outcome": "Recommend which formats to scale, revise, or retire using retention, review quality, production cost, and demand evidence."},
        ],
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
