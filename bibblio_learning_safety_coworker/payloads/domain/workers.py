from __future__ import annotations

from collections import Counter
from typing import Any

from .collaboration import build_packet, peer_signals, persist_packet, write_final_artifact
from .common import BLOCKED_ACTIONS
from .inputs import json_object, resolve_input_file, source_descriptor


def run_learning_safety_director(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "review_learning_backlog":
        return _review_backlog(context)
    if step_id == "publish_learning_safety_packet":
        return _publish_learning_packet(context)
    raise ValueError(f"Learning-safety co-worker does not own step {step_id!r}")


def _dataset(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    path = resolve_input_file(context, "content_backlog_file", "content_backlog.json")
    payload = json_object(path)
    items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
    synthetic = str(payload.get("data_status") or "").lower() == "synthetic_demo" or any(
        str(item.get("data_status") or "").lower() == "synthetic_demo" for item in items
    )
    return items, source_descriptor(path, synthetic=synthetic), synthetic


def _review_backlog(context: dict[str, Any]) -> dict[str, Any]:
    items, source, synthetic = _dataset(context)
    reviewed = [_review_item(item) for item in items]
    decisions = Counter(item["decision"] for item in reviewed)
    peers = peer_signals(context)
    packet = build_packet(
        context,
        stage="review_learning_backlog",
        objective="Map every proposed Bibblio content item to an observable learning objective and block unsafe, unsuitable, or unsupported claims.",
        trigger="A learning or content backlog is submitted for curriculum and child-safety review.",
        sources=[source],
        observed_facts=[
            f"The supplied backlog contains {len(reviewed)} items.",
            f"Review decisions: {dict(decisions)}.",
            *[f"Blocked {item['content_id']}: {item['reason']}" for item in reviewed if item["decision"] == "BLOCK"],
        ],
        assumptions=["Age bands, objectives, answer logic, and personalization fields are drafts until a qualified human reviews the complete content package."],
        analysis={
            "reviewed_backlog": reviewed,
            "decision_counts": dict(decisions),
            "peer_goal_packet_count": len(peers["signals"]),
            "peer_goal_signals": peers["signals"],
            "blocked_actions": BLOCKED_ACTIONS,
        },
        recommendation="Allow only complete observable learning briefs to proceed; quarantine blocked or therapeutic proposals and require full-package review before publication.",
        confidence="low" if synthetic else "medium",
        risks=["A safe brief does not guarantee safe generated text, images, audio, or interactions.", "Observational engagement does not prove learning causation."],
        requested_approval=["A qualified learning and safety reviewer approves every objective, age band, sensitive topic, answer key, and child-facing release."],
        outputs=["curriculum review register", "PASS/REVISE/BLOCK queue", "safety escalation list"],
        next_check="Before content generation, after material revisions, and before publication.",
    )
    return persist_packet(context, packet)


def _publish_learning_packet(context: dict[str, Any]) -> dict[str, Any]:
    items, source, synthetic = _dataset(context)
    reviewed = [_review_item(item) for item in items]
    decisions = Counter(item["decision"] for item in reviewed)
    packet = build_packet(
        context,
        stage="publish_learning_safety_packet",
        objective="Publish the authoritative learning and safety gate for peer co-workers and founder review.",
        trigger="The deterministic backlog review is complete.",
        sources=[source],
        observed_facts=[f"{decisions.get('BLOCK', 0)} items are blocked and {decisions.get('REVISE', 0)} require revision."],
        assumptions=["The packet covers only the supplied backlog fields, not a complete release candidate."],
        analysis={"reviewed_backlog": reviewed, "decision_counts": dict(decisions), "publication_authorized": False},
        recommendation="Use PASS or PASS WITH CONDITIONS items only as inputs to draft production; do not publish until complete content and human review are available.",
        confidence="low" if synthetic else "medium",
        risks=["Missing images, audio, interactions, answer keys, or personalization substitutions can introduce new defects."],
        requested_approval=["Founder and qualified learning/safety reviewers approve any child-facing release."],
        outputs=["learning and safety decision packet", "blocked item queue"],
        next_check="When the Content Studio returns a complete review bundle.",
        publication_state="final",
    )
    persisted = persist_packet(context, packet)
    final = write_final_artifact(
        context,
        packet,
        artifact_type="bibblio_learning_safety_decision_packet",
        executive_summary="The learning-safety co-worker independently reviewed the supplied backlog, recorded PASS/REVISE/BLOCK decisions, and kept publication behind qualified human approval.",
        evidence={"decision_counts": dict(decisions), "reviewed_backlog": reviewed, "publication_authorized": False},
        next_steps=[
            "Resolve every REVISE condition and quarantine every BLOCK item.",
            "Send approved learning briefs—not raw child data—to the Content Studio co-worker.",
            "Review complete release candidates including text, visuals, audio, activities, and answer keys.",
            "Monitor post-release defects without claiming causation from weak observational data.",
        ],
        data_status="synthetic_demo" if synthetic else "user_supplied",
    )
    return {**persisted, **final}


def _review_item(item: dict[str, Any]) -> dict[str, Any]:
    content_id = str(item.get("id") or "unknown")
    objective = str(item.get("learning_objective") or "").strip()
    age_band = str(item.get("age_band") or "").strip()
    claim_risk = str(item.get("claim_risk") or "unknown").lower()
    text = " ".join(str(value or "") for value in (item.get("title"), objective, item.get("parent_value"))).lower()
    therapeutic = claim_risk == "blocked" or any(term in text for term in ("treat ", "therapy", "diagnose", "cure "))
    if therapeutic:
        decision = "BLOCK"
        reason = "Therapeutic, diagnostic, medical, or explicitly blocked claims require rejection and qualified human review."
    elif not objective or not age_band:
        decision = "REVISE"
        reason = "A complete observable objective and age band are required."
    elif bool(item.get("sensitive_topic")):
        decision = "PASS WITH CONDITIONS"
        reason = "The brief may proceed only with explicit sensitive-topic rules and complete human review."
    else:
        decision = "PASS"
        reason = "The brief clears deterministic intake checks; full-package learning and safety review remains required."
    return {
        "content_id": content_id,
        "title": str(item.get("title") or "Untitled"),
        "age_band": age_band or "not_reported",
        "learning_objective": objective,
        "decision": decision,
        "reason": reason,
        "required_human_review": True,
    }
