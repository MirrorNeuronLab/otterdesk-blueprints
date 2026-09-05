"""Model and deterministic final checks before any advisory artifact is published."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_analysis import (
    STAGES,
    fake_mode,
    known_fact_ids,
    known_paths,
    run_model_stage,
    string_list,
    structured_packet,
    text,
    validate_references,
)
from .report_drafting import SECTION_NAMES
from .state import read_state, write_state

_AUDIT_CHECKS = (
    "claims_are_fact_grounded",
    "metrics_are_deterministic",
    "adversarial_dispositions_are_complete",
    "prompts_are_safe_and_reversible",
    "report_coverage_is_complete",
)


def audit_advice(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = read_state(ctx)
    preliminary = _deterministic_checks(ctx, state, include_final_usage=False)
    known = known_fact_ids(state)
    fallback_verdict = "approve" if all(item["passed"] for item in preliminary) else "reject"
    fallback = {
        "verdict": fallback_verdict,
        "summary": "The complete draft package is approved only when every deterministic grounding, coverage, usage, and safety check passes.",
        "checks": [
            {
                "name": name,
                "status": fallback_verdict,
                "rationale": "Deterministic package checks passed." if fallback_verdict == "approve" else "One or more deterministic package checks require revision.",
                "fact_ids": sorted(known)[:20],
            }
            for name in _AUDIT_CHECKS
        ],
        "rejected_claims": [],
        "required_revisions": [] if fallback_verdict == "approve" else [item["name"] for item in preliminary if not item["passed"]],
    }
    audit_context = structured_packet(
        state,
        preliminary_checks=preliminary,
        deterministic_gate=_deterministic_gate(preliminary),
        report_draft=_audit_report_summary(state.get("report_draft") or {}),
        findings=[_audit_finding_summary(item) for item in state.get("findings") or []],
        prompts=[_audit_prompt_summary(item) for item in state.get("prompt_pack") or []],
        adversarial_review=_audit_review_summary(state.get("adversarial_review") or {}),
        prior_llm_stages=_prior_stage_summaries(state),
    )
    final_model_audit = run_model_stage(
        ctx,
        state,
        stage="final_audit",
        task=(
            "Apply the deterministic_gate to the complete package. If all preliminary "
            "checks pass, approve all five model checks; otherwise reject and name the "
            "failed checks. Reject unsupported claims, unresolved citations, altered "
            "metrics, unsafe prompts, missing adversarial dispositions, or missing "
            "report coverage. Treat explicitly unavailable runtime evidence as a stated "
            "limitation, not as a failure."
        ),
        context=audit_context,
        fallback=fallback,
        validator=lambda value: _validate_model_audit(
            value,
            fact_ids=known,
            deterministic_gate=audit_context["deterministic_gate"],
            supplied_context=audit_context,
            fallback=fallback,
        ),
        llm_client=llm_client,
    )
    checks = _deterministic_checks(ctx, state, include_final_usage=True)
    checks.append({"name": "model_final_audit_approved", "passed": final_model_audit["verdict"] == "approve"})
    audit = {
        "status": "passed" if all(item["passed"] for item in checks) else "needs_revision",
        "checks": checks,
        "model_audit": final_model_audit,
        "review_required": True,
        "publication_authorized": all(item["passed"] for item in checks),
    }
    state["audit"] = audit
    write_state(ctx, state)
    if audit["status"] != "passed":
        failed = ", ".join(item["name"] for item in checks if not item["passed"])
        raise ValueError(f"Architecture advice failed final audit: {failed}")
    return audit


def _deterministic_gate(preliminary: list[dict[str, Any]]) -> dict[str, Any]:
    """Give the model an explicit, machine-generated decision basis.

    The final model pass supplies an independent narrative audit, but it must
    not invent extra gates from explicitly unavailable runtime evidence. The
    deterministic checks are the authoritative publication precondition.
    """
    failed = [item["name"] for item in preliminary if not item.get("passed")]
    return {
        "all_preliminary_checks_pass": not failed,
        "failed_preliminary_checks": failed,
        "approval_rule": (
            "If all_preliminary_checks_pass is true, return verdict approve and "
            "status approve for all five required model checks. If it is false, "
            "return verdict reject and identify the failed checks. Do not add a "
            "new rejection condition based only on evidence explicitly marked "
            "unavailable or unknown."
        ),
        "publication_remains_deterministic": True,
    }


def _prior_stage_summaries(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expose completion evidence to the auditor without replaying model outputs."""
    stages = ((state.get("llm_analysis") or {}).get("stages") or {})
    allowed = (
        "stage", "stage_index", "actor", "status", "provider", "model",
        "estimated_input_tokens", "input_token_budget", "reserved_completion_tokens",
        "input_tokens", "output_tokens", "provider_response_count",
        "validation_retries", "fallback",
    )
    return {
        name: {key: record.get(key) for key in allowed if key in record}
        for name in STAGES
        if name != "final_audit" and isinstance((record := stages.get(name)), dict)
    }


def _audit_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    sections = report.get("sections") if isinstance(report.get("sections"), dict) else {}
    return {
        "sections": {
            name: {
                "text": text((item or {}).get("text"), maximum=2400),
                "text_truncated_for_audit": len(str((item or {}).get("text") or "")) > 2400,
                "fact_ids": list((item or {}).get("fact_ids") or []),
            }
            for name, item in sections.items()
            if isinstance(item, dict)
        },
        "coverage": list(report.get("coverage") or []),
    }


def _audit_finding_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    review = item.get("adversarial_review") if isinstance(item.get("adversarial_review"), dict) else {}
    return {
        "finding_id": item.get("finding_id"),
        "title": text(item.get("title"), maximum=500),
        "summary": text(item.get("summary"), maximum=1200),
        "interpretation": text(item.get("interpretation"), maximum=1200),
        "recommendation": text(item.get("recommendation"), maximum=1200),
        "severity": item.get("severity"),
        "confidence": item.get("confidence"),
        "origin": item.get("origin"),
        "evidence": {
            "fact_ids": list(evidence.get("fact_ids") or []),
            "paths": list(evidence.get("paths") or []),
            "signal_types": list(evidence.get("signal_types") or []),
        },
        "counter_evidence_considered": list(item.get("counter_evidence_considered") or [])[:12],
        "alternative_options": [
            {
                "option_id": option.get("option_id"),
                "title": text(option.get("title"), maximum=400),
                "tradeoffs": text(option.get("tradeoffs"), maximum=800),
                "recommended": bool(option.get("recommended")),
            }
            for option in item.get("alternative_options") or []
            if isinstance(option, dict)
        ][:8],
        "migration_risk": text(item.get("migration_risk"), maximum=800),
        "rollback_considerations": text(item.get("rollback_considerations"), maximum=800),
        "stop_conditions": list(item.get("stop_conditions") or [])[:12],
        "adversarial_disposition": {
            "verdict": review.get("verdict"),
            "rationale": text(review.get("rationale"), maximum=800),
            "fact_ids": list(review.get("fact_ids") or []),
        },
    }


def _audit_prompt_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    body = str(item.get("body") or "")
    required_sections = (
        "Architecture intent", "Counter-evidence to check", "Migration sequence",
        "Tests", "Non-goals and safeguards", "Rollback considerations", "Stop conditions",
    )
    return {
        key: item.get(key)
        for key in ("prompt_id", "finding_id", "title", "priority", "severity", "confidence", "fact_ids", "origin")
    } | {
        "body_chars": len(body),
        "required_sections_present": {
            name: f"## {name}" in body for name in required_sections
        },
        "safety_and_reversibility_excerpt": "\n\n".join(
            value for name in ("Tests", "Non-goals and safeguards", "Rollback considerations", "Stop conditions")
            if (value := _markdown_section(body, name, maximum=1400))
        ),
    }


def _markdown_section(body: str, name: str, *, maximum: int) -> str:
    marker = f"## {name}"
    start = body.find(marker)
    if start < 0:
        return ""
    end = body.find("\n## ", start + len(marker))
    return text(body[start:end if end >= 0 else None], maximum=maximum)


def _audit_review_summary(review: Any) -> dict[str, Any]:
    if not isinstance(review, dict):
        return {}
    return {
        "summary": text(review.get("summary"), maximum=1600),
        "finding_reviews": [
            {
                "finding_id": item.get("finding_id"),
                "verdict": item.get("verdict"),
                "revised_severity": item.get("revised_severity"),
                "revised_confidence": item.get("revised_confidence"),
                "rationale": text(item.get("rationale"), maximum=1000),
                "fact_ids": list(item.get("fact_ids") or []),
                "missing_evidence": list(item.get("missing_evidence") or [])[:12],
            }
            for item in review.get("finding_reviews") or []
            if isinstance(item, dict)
        ],
        "required_human_checks": list(review.get("required_human_checks") or [])[:20],
    }


def _deterministic_checks(
    ctx: dict[str, Any], state: dict[str, Any], *, include_final_usage: bool
) -> list[dict[str, Any]]:
    findings = state.get("findings") or []
    prompts = state.get("prompt_pack") or []
    facts = known_fact_ids(state)
    paths = known_paths(state)
    reviews = {
        item.get("finding_id"): item
        for item in ((state.get("adversarial_review") or {}).get("finding_reviews") or [])
    }
    draft = state.get("report_draft") or {}
    sections = draft.get("sections") if isinstance(draft.get("sections"), dict) else {}
    analysis = state.get("llm_analysis") or {}
    aggregate = analysis.get("aggregate_usage") or {}
    quick = fake_mode(ctx.get("config") or {})
    checks = [
        {"name": "source_was_not_executed", "passed": (state.get("source") or {}).get("source_execution") == "forbidden"},
        {"name": "network_egress_forbidden", "passed": (state.get("source") or {}).get("network_egress") == "forbidden"},
        {"name": "findings_have_evidence", "passed": bool(findings) and all((item.get("evidence") or {}).get("fact_ids") for item in findings)},
        {"name": "finding_origins_are_declared", "passed": all(item.get("origin") in {"deterministic", "llm_grounded"} for item in findings)},
        {"name": "finding_fact_ids_resolve", "passed": all(set((item.get("evidence") or {}).get("fact_ids") or []).issubset(facts) for item in findings)},
        {"name": "finding_paths_exist", "passed": all(set((item.get("evidence") or {}).get("paths") or []).issubset(paths) for item in findings)},
        {"name": "high_findings_are_triangulated", "passed": all(item.get("severity") not in {"high", "critical"} or len(set((item.get("evidence") or {}).get("signal_types") or [])) >= 2 for item in findings)},
        {"name": "adversarial_reviews_cover_findings", "passed": all(item["finding_id"] in reviews and reviews[item["finding_id"]].get("verdict") != "reject" for item in findings)},
        {"name": "counter_evidence_was_considered", "passed": all(bool(item.get("counter_evidence_considered")) for item in findings)},
        {"name": "findings_offer_options", "passed": all(len(item.get("alternative_options") or []) >= 2 for item in findings)},
        {"name": "prompts_cover_findings", "passed": {item.get("finding_id") for item in prompts} == {item.get("finding_id") for item in findings}},
        {"name": "prompts_include_safeguards", "passed": all(all(section in item.get("body", "") for section in ("Architecture intent", "Counter-evidence to check", "Migration sequence", "Tests", "Non-goals and safeguards", "Rollback considerations", "Stop conditions")) for item in prompts)},
        {"name": "report_coverage_is_complete", "passed": set(sections) == set(SECTION_NAMES) and set(draft.get("coverage") or []) == set(SECTION_NAMES)},
        {"name": "report_fact_ids_resolve", "passed": all(set((item or {}).get("fact_ids") or []).issubset(facts) for item in sections.values())},
        {"name": "llm_trace_is_metadata_only", "passed": _trace_is_metadata_only(Path(ctx["run_dir"]) / "llm_trace.jsonl")},
    ]
    if include_final_usage:
        stages = analysis.get("stages") if isinstance(analysis.get("stages"), dict) else {}
        checks.extend([
            {"name": "all_eight_llm_stages_completed", "passed": list(stages) == list(STAGES) and all((stages[name] or {}).get("status") in {"completed", "completed_fake"} for name in STAGES)},
            {"name": "llm_action_budget_exact", "passed": int(aggregate.get("calls") or 0) == len(STAGES)},
            {"name": "live_llm_fallbacks_absent", "passed": quick or int(aggregate.get("fallback_calls") or 0) == 0},
            {"name": "live_provider_responses_present", "passed": quick or int(aggregate.get("provider_response_count") or 0) >= len(STAGES)},
            {"name": "live_provider_tokens_present", "passed": quick or (int(aggregate.get("input_tokens") or 0) > 0 and int(aggregate.get("output_tokens") or 0) > 0)},
        ])
    return checks


def _validate_model_audit(
    value: dict[str, Any], *, fact_ids: set[str],
    deterministic_gate: dict[str, Any], supplied_context: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    verdict = str(value.get("verdict") or "").lower()
    raw_checks = value.get("checks")
    if verdict not in {"approve", "reject"} or not isinstance(raw_checks, list):
        return None
    checks = []
    seen = set()
    for item in raw_checks:
        if not isinstance(item, dict):
            return None
        name = str(item.get("name") or "")
        status = str(item.get("status") or "").lower()
        cited = validate_references(item.get("fact_ids"), fact_ids)
        if name not in _AUDIT_CHECKS or name in seen or status not in {"approve", "reject"} or cited is None:
            return None
        seen.add(name)
        checks.append({"name": name, "status": status, "rationale": text(item.get("rationale"), maximum=1800), "fact_ids": cited})
    if seen != set(_AUDIT_CHECKS):
        return None
    rejected = string_list(value.get("rejected_claims"), maximum_items=20)
    revisions = string_list(value.get("required_revisions"), maximum_items=20)
    summary = text(value.get("summary"), maximum=3600)
    if rejected is None or revisions is None or not summary:
        return None
    if verdict == "approve" and any(item["status"] != "approve" for item in checks):
        return None
    gate_passed = bool(deterministic_gate.get("all_preliminary_checks_pass"))
    if gate_passed and verdict == "reject":
        # A final model can still veto a deterministically valid package, but
        # the veto must identify an actual supplied claim. This prevents
        # explicitly unavailable runtime evidence from becoming an invented
        # publication requirement while preserving a concrete safety veto.
        supplied = json.dumps(supplied_context, sort_keys=True, default=str).casefold()
        concrete = [
            claim
            for claim in rejected
            if len(claim.strip()) >= 16 and claim.strip().casefold() in supplied
        ]
        if not concrete:
            return dict(fallback)
    if not gate_passed and verdict == "approve":
        return dict(fallback)
    return {"verdict": verdict, "summary": summary, "checks": checks, "rejected_claims": rejected, "required_revisions": revisions}


def _trace_is_metadata_only(path: Path) -> bool:
    if not path.is_file():
        return False
    forbidden = {"prompt", "system_prompt", "user_prompt", "bounded_context", "context", "excerpt", "source", "response", "output"}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return False
        if _contains_forbidden_key(value, forbidden):
            return False
    return True


def _contains_forbidden_key(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in forbidden or _contains_forbidden_key(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


__all__ = ["audit_advice"]
