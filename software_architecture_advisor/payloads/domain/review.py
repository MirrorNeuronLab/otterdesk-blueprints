"""Required synthesis and adversarial review over authoritative static facts."""

from __future__ import annotations

from typing import Any

from .findings import build_findings, build_llm_grounded_finding
from .model_analysis import (
    known_fact_ids,
    known_paths,
    run_model_stage,
    string_list,
    structured_packet,
    text,
    validate_references,
)
from .state import read_state, write_state


def assess_architecture(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = read_state(ctx)
    config = ctx.get("config") or {}
    deterministic = build_findings(state, config.get("analysis") or {})
    deterministic_ids = {item["finding_id"] for item in deterministic}
    fact_ids = known_fact_ids(state)
    paths = known_paths(state)
    synthesis_fallback = {
        "summary": "Deterministic candidates were retained as architecture hypotheses pending adversarial review and current-checkout verification.",
        "deterministic_finding_rationales": [
            {
                "finding_id": item["finding_id"],
                "rationale": item["why_it_matters"],
                "tradeoffs": [option["tradeoffs"] for option in item["alternative_options"]],
                "migration_risks": [item["migration_risk"]],
                "fact_ids": list(item["evidence"]["fact_ids"]),
            }
            for item in deterministic
        ],
        "grounded_findings": [],
    }
    synthesis = run_model_stage(
        ctx,
        state,
        stage="finding_synthesis",
        task="Combine static candidates with grounded new findings, alternatives, tradeoffs, and migration risks.",
        context=structured_packet(
            state,
            component_map=state.get("architecture_reconstruction") or {},
            cross_cutting_analysis=state.get("cross_cutting_analysis") or {},
            deterministic_findings=deterministic,
        ),
        fallback=synthesis_fallback,
        validator=lambda value: _validate_synthesis(
            value,
            deterministic_ids=deterministic_ids,
            fact_ids=fact_ids,
            paths=paths,
            state=state,
        ),
        llm_client=llm_client,
    )
    rationales = {item["finding_id"]: item for item in synthesis["deterministic_finding_rationales"]}
    for finding in deterministic:
        rationale = rationales[finding["finding_id"]]
        finding["llm_rationale"] = rationale["rationale"]
        finding["llm_tradeoffs"] = rationale["tradeoffs"]
        finding["llm_migration_risks"] = rationale["migration_risks"]
    grounded = [
        build_llm_grounded_finding(state, item, index)
        for index, item in enumerate(synthesis["grounded_findings"], start=1)
        if item["finding_id"] not in deterministic_ids
    ]
    candidates = [*deterministic, *grounded]
    adversarial_fallback = {
        "summary": "Every candidate remains bounded by static evidence and must be verified against runtime, ownership, and current-checkout context.",
        "finding_reviews": [
            {
                "finding_id": item["finding_id"],
                "verdict": "retain",
                "revised_severity": item["severity"],
                "revised_confidence": item["confidence"],
                "rationale": "The cited static evidence supports retaining this item as a review hypothesis, not as runtime proof.",
                "fact_ids": list(item["evidence"]["fact_ids"]),
                "missing_evidence": ["runtime behavior", "production ownership", "executed tests"],
            }
            for item in candidates
        ],
        "required_human_checks": [
            "Confirm runtime composition and state authority with maintainers.",
            "Validate every cited fact and path in the current checkout before implementation.",
        ],
    }
    candidate_ids = {item["finding_id"] for item in candidates}
    adversarial = run_model_stage(
        ctx,
        state,
        stage="adversarial_review",
        task="Challenge, revise, downgrade, or reject every finding.",
        context=structured_packet(
            state,
            candidate_findings=candidates,
            evidence_availability=state.get("evidence_availability") or {},
        ),
        fallback=adversarial_fallback,
        validator=lambda value: _validate_adversarial(value, candidate_ids=candidate_ids, fact_ids=fact_ids),
        llm_client=llm_client,
    )
    reviews = {item["finding_id"]: item for item in adversarial["finding_reviews"]}
    surviving = []
    for finding in candidates:
        review = reviews[finding["finding_id"]]
        finding["adversarial_review"] = review
        if review["verdict"] == "reject":
            continue
        if review["verdict"] in {"revise", "downgrade"}:
            finding["severity"] = _safe_revised_severity(finding, review["revised_severity"])
            finding["confidence"] = review["revised_confidence"]
        surviving.append(finding)
    if not surviving:
        raise ValueError("Adversarial review rejected every finding; no implementation advice can be published.")
    state["findings"] = surviving
    state["finding_synthesis"] = synthesis
    state["adversarial_review"] = adversarial
    state["actor_review"] = {"finding_synthesis": synthesis, "adversarial_review": adversarial}
    write_state(ctx, state)
    return {
        "finding_count": len(surviving),
        "llm_grounded_finding_count": sum(item.get("origin") == "llm_grounded" for item in surviving),
        "priorities": [item["finding_id"] for item in surviving],
        "high_confidence_count": sum(item["confidence"] == "high" for item in surviving),
    }


def _validate_synthesis(
    value: dict[str, Any], *, deterministic_ids: set[str], fact_ids: set[str],
    paths: set[str], state: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_rationales = value.get("deterministic_finding_rationales")
    if not isinstance(raw_rationales, list):
        return None
    rationales = []
    seen = set()
    for item in raw_rationales:
        if not isinstance(item, dict):
            return None
        finding_id = str(item.get("finding_id") or "")
        cited = validate_references(item.get("fact_ids"), fact_ids, allow_empty=False)
        tradeoffs = string_list(item.get("tradeoffs"), maximum_items=12)
        risks = string_list(item.get("migration_risks"), maximum_items=12)
        rationale = text(item.get("rationale"), maximum=2600)
        if finding_id not in deterministic_ids or finding_id in seen or cited is None or tradeoffs is None or risks is None or not rationale:
            return None
        seen.add(finding_id)
        rationales.append({"finding_id": finding_id, "rationale": rationale, "tradeoffs": tradeoffs, "migration_risks": risks, "fact_ids": cited})
    if seen != deterministic_ids:
        return None
    grounded = []
    raw_grounded = value.get("grounded_findings")
    if not isinstance(raw_grounded, list):
        return None
    evidence_types = {
        str(item.get("fact_id")): str(item.get("evidence_type") or "")
        for item in ((state.get("architecture_facts") or {}).get("facts") or [])
    }
    fact_paths = {
        str(item.get("fact_id")): set(item.get("paths") or [])
        for item in ((state.get("architecture_facts") or {}).get("facts") or [])
    }
    for item in raw_grounded[:8]:
        normalized = _validate_grounded_finding(item, fact_ids=fact_ids, paths=paths)
        if normalized is None:
            return None
        signals = {evidence_types.get(fact_id) for fact_id in normalized["fact_ids"] if evidence_types.get(fact_id)}
        finding_paths = set(normalized["paths"])
        if any(fact_paths.get(fact_id) and not fact_paths[fact_id].intersection(finding_paths) for fact_id in normalized["fact_ids"]):
            return None
        if normalized["severity"] in {"high", "critical"} and len(signals) < 2:
            return None
        grounded.append(normalized)
    summary = text(value.get("summary"), maximum=4500)
    if not summary:
        return None
    return {"summary": summary, "deterministic_finding_rationales": rationales, "grounded_findings": grounded}


def _validate_grounded_finding(item: Any, *, fact_ids: set[str], paths: set[str]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    cited = validate_references(item.get("fact_ids"), fact_ids, allow_empty=False)
    cited_paths = validate_references(item.get("paths"), paths, allow_empty=False)
    migration = string_list(item.get("migration_sequence"), maximum_items=15)
    tests = string_list(item.get("test_strategy"), maximum_items=15)
    stops = string_list(item.get("stop_conditions"), maximum_items=12)
    counter = string_list(item.get("counter_evidence_considered"), maximum_items=12)
    raw_options = item.get("alternative_options")
    if cited is None or cited_paths is None or migration is None or tests is None or stops is None or counter is None or not isinstance(raw_options, list) or len(raw_options) < 2:
        return None
    options = []
    for index, option in enumerate(raw_options[:5]):
        if not isinstance(option, dict):
            return None
        options.append({
            "option_id": text(option.get("option_id"), maximum=20) or chr(65 + index),
            "title": text(option.get("title"), maximum=300),
            "direction": text(option.get("direction"), maximum=1400),
            "tradeoffs": text(option.get("tradeoffs"), maximum=1400),
            "recommended": bool(option.get("recommended", index == 0)),
        })
    required_text = {
        key: text(item.get(key), maximum=2600)
        for key in ("finding_id", "title", "category", "summary", "interpretation", "why_it_matters", "recommendation", "rollback_considerations")
    }
    if not all(required_text.values()):
        return None
    severity = text(item.get("severity"), maximum=20).lower()
    if severity not in {"low", "medium", "high", "critical"}:
        return None
    return {
        **required_text,
        "severity": severity,
        "fact_ids": cited,
        "paths": cited_paths,
        "alternative_options": options,
        "counter_evidence_considered": [{"check": value, "status": "model_considered"} for value in counter],
        "migration_risk": text(item.get("migration_risk"), maximum=30) or "medium",
        "migration_sequence": migration,
        "test_strategy": tests,
        "stop_conditions": stops,
    }


def _validate_adversarial(value: dict[str, Any], *, candidate_ids: set[str], fact_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("finding_reviews"), list):
        return None
    reviews = []
    seen = set()
    for item in value["finding_reviews"]:
        if not isinstance(item, dict):
            return None
        finding_id = str(item.get("finding_id") or "")
        verdict = str(item.get("verdict") or "").lower()
        severity = str(item.get("revised_severity") or "").lower()
        confidence = str(item.get("revised_confidence") or "").lower()
        cited = validate_references(item.get("fact_ids"), fact_ids, allow_empty=False)
        missing = string_list(item.get("missing_evidence"), maximum_items=15)
        if finding_id not in candidate_ids or finding_id in seen or verdict not in {"retain", "revise", "downgrade", "reject"} or severity not in {"low", "medium", "high", "critical"} or confidence not in {"low", "medium", "high"} or cited is None or missing is None:
            return None
        seen.add(finding_id)
        reviews.append({
            "finding_id": finding_id,
            "verdict": verdict,
            "revised_severity": severity,
            "revised_confidence": confidence,
            "rationale": text(item.get("rationale"), maximum=2400),
            "fact_ids": cited,
            "missing_evidence": missing,
        })
    if seen != candidate_ids:
        return None
    checks = string_list(value.get("required_human_checks"), maximum_items=20)
    summary = text(value.get("summary"), maximum=4000)
    if checks is None or not summary:
        return None
    return {"summary": summary, "finding_reviews": reviews, "required_human_checks": checks}


def _safe_revised_severity(finding: dict[str, Any], requested: str) -> str:
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    signal_count = len(set((finding.get("evidence") or {}).get("signal_types") or []))
    if requested in {"critical", "high"} and signal_count < 2:
        return "medium"
    if rank.get(requested, 0) > rank.get(str(finding.get("severity")), 0):
        return str(finding.get("severity"))
    return requested
