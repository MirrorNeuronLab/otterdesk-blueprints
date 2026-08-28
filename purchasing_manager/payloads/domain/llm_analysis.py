"""Bounded, interpretive LLM analysis over authoritative procurement results."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Callable

from mn_blueprint_support import llm_usage

from .common import _sha256, load_prompt, purchase_llm, quick_test_enabled


MAX_LLM_CALLS = 5
SELECTED_AGENT_IDS = (
    "purchase_intake_analyst",
    "purchase_total_cost_analyst",
    "purchase_risk_reviewer",
    "purchase_recommendation_auditor",
    "purchase_report_writer",
)

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
_TCO_KEYS = (
    "base_purchase_price",
    "vendor_cash_cost",
    "landed_acquisition_cost",
    "internal_implementation_cost",
    "annual_energy_cost",
    "annual_financial_operating_cost",
    "annual_downtime_exposure",
    "annual_risk_exposure",
    "residual_value",
    "financial_npv_tco",
    "risk_adjusted_npv_tco",
    "equivalent_annual_cost",
    "risk_adjusted_cost_per_productive_hour",
)
_SCENARIO_KEYS = (
    "financial_npv_tco",
    "risk_adjusted_npv_tco",
    "equivalent_annual_cost",
    "annual_energy_cost",
    "annual_downtime_exposure",
    "residual_value",
)
_METHOD_KEYS = (
    "status",
    "monthly_payment",
    "nominal_cash_outflow",
    "present_value_cost",
    "incremental_present_value_vs_cash",
    "missing_terms",
)


def analysis_settings(config: dict[str, Any]) -> dict[str, int]:
    raw = config.get("llm_analysis") if isinstance(config.get("llm_analysis"), dict) else {}
    return {
        "max_calls_per_run": min(MAX_LLM_CALLS, max(1, int(raw.get("max_calls_per_run") or MAX_LLM_CALLS))),
        "max_context_chars": min(60000, max(6000, int(raw.get("max_context_chars") or 30000))),
        "max_candidates": min(20, max(1, int(raw.get("max_candidates") or 8))),
        "max_list_items": min(20, max(1, int(raw.get("max_list_items") or 10))),
        "max_text_chars": min(4000, max(200, int(raw.get("max_text_chars") or 1600))),
    }


def llm_agent_selected(config: dict[str, Any], agent_id: str) -> bool:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    spec = agents.get(agent_id) if isinstance(agents.get(agent_id), dict) else {}
    return (
        bool(llm.get("enabled", True))
        and spec.get("enabled", True) is not False
        and agent_id in SELECTED_AGENT_IDS
    )


def _canonical_numbers(value: Any) -> set[str]:
    text = json.dumps(value, sort_keys=True, default=str)
    values: set[str] = set()
    for token in _NUMBER_RE.findall(text):
        cleaned = token.replace("$", "").replace(",", "").removesuffix("%")
        try:
            values.add(f"{float(cleaned):.12g}")
        except ValueError:
            continue
    return values


def _has_unknown_number(text: str, allowed_numbers: set[str]) -> bool:
    for token in _NUMBER_RE.findall(text):
        cleaned = token.replace("$", "").replace(",", "").removesuffix("%")
        try:
            canonical = f"{float(cleaned):.12g}"
        except ValueError:
            continue
        if canonical not in allowed_numbers:
            return True
    return False


def _text(
    value: Any,
    fallback: str,
    *,
    field: str,
    allowed_numbers: set[str],
    errors: list[str],
    max_chars: int,
) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return fallback
    if _has_unknown_number(candidate, allowed_numbers):
        errors.append(f"{field}: unsupported numeric claim")
        return fallback
    return candidate[:max_chars]


def _string_list(
    value: Any,
    fallback: list[str],
    *,
    field: str,
    allowed_numbers: set[str],
    errors: list[str],
    max_items: int,
    max_chars: int,
) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    result: list[str] = []
    for index, item in enumerate(value[:max_items]):
        candidate = str(item or "").strip()
        if not candidate:
            continue
        if _has_unknown_number(candidate, allowed_numbers):
            errors.append(f"{field}[{index}]: unsupported numeric claim")
            continue
        result.append(candidate[:max_chars])
    return result if result else list(fallback)


def _reference_list(
    value: Any,
    fallback: list[str],
    *,
    field: str,
    allowed: set[str],
    errors: list[str],
    max_items: int,
) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    result: list[str] = []
    for item in value[:max_items]:
        ref = str(item or "").strip()
        if not ref:
            continue
        if ref not in allowed:
            errors.append(f"{field}: unknown reference")
            continue
        result.append(ref)
    return list(dict.fromkeys(result))


def known_source_refs(state: dict[str, Any]) -> set[str]:
    refs: set[str] = {"inputs.json", "events.jsonl", "result.json"}

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            refs.add(value.strip())
        elif isinstance(value, dict):
            for key in ("source_ref", "url", "source_url", "path", "ref"):
                add(value.get(key))
        elif isinstance(value, list):
            for item in value:
                add(item)

    add((state.get("evidence") or {}).get("source_refs"))
    add((state.get("rag") or {}).get("citations"))
    add(state.get("sources"))
    for candidate in state.get("candidate_comparisons") or []:
        if isinstance(candidate, dict):
            add(candidate.get("source_ref"))
            add(candidate.get("source_url"))
            add(candidate.get("source_urls"))
    return refs


def candidate_analysis_packet(
    comparisons: list[dict[str, Any]], *, max_candidates: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packet: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    for candidate in comparisons[:max_candidates]:
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            continue
        candidate_packet: dict[str, Any] = {
            "candidate_id": candidate_id,
            "label": candidate.get("label"),
            "vendor": candidate.get("vendor"),
            "hard_constraints_passed": bool(candidate.get("hard_constraints_passed")),
            "failed_hard_constraints": [
                key
                for key, passed in (candidate.get("hard_constraint_checks") or {}).items()
                if not passed
            ],
            "source_refs": list(
                dict.fromkeys(
                    filter(
                        None,
                        [
                            candidate.get("source_ref"),
                            candidate.get("source_url"),
                            *(candidate.get("source_urls") or []),
                        ],
                    )
                )
            ),
            "metrics": {},
            "scenarios": [],
            "acquisition_methods": [],
        }
        tco = candidate.get("tco") if isinstance(candidate.get("tco"), dict) else {}
        for key in _TCO_KEYS:
            if key in tco and tco[key] is not None:
                ref = f"candidate.{candidate_id}.tco.{key}"
                metrics[ref] = tco[key]
                candidate_packet["metrics"][ref] = tco[key]
        for key in (
            "asking_price",
            "known_upfront_cost",
            "known_annual_carry",
            "known_five_year_cost_before_financing_utilities_and_resale",
        ):
            if candidate.get(key) is not None:
                ref = f"candidate.{candidate_id}.{key}"
                metrics[ref] = candidate[key]
                candidate_packet["metrics"][ref] = candidate[key]
        for index, scenario in enumerate(candidate.get("scenario_analysis") or []):
            if not isinstance(scenario, dict):
                continue
            scenario_packet = {"name": scenario.get("name"), "metric_refs": []}
            for key in _SCENARIO_KEYS:
                if scenario.get(key) is not None:
                    ref = f"candidate.{candidate_id}.scenario.{index}.{key}"
                    metrics[ref] = scenario[key]
                    scenario_packet["metric_refs"].append(ref)
            candidate_packet["scenarios"].append(scenario_packet)
        for method in candidate.get("acquisition_method_analysis") or []:
            if not isinstance(method, dict):
                continue
            method_name = str(method.get("method") or "unknown")
            method_packet = {"method": method_name, "metric_refs": []}
            for key in _METHOD_KEYS:
                if method.get(key) is not None:
                    ref = f"candidate.{candidate_id}.acquisition_method.{method_name}.{key}"
                    metrics[ref] = method[key]
                    method_packet["metric_refs"].append(ref)
            candidate_packet["acquisition_methods"].append(method_packet)
        packet.append(candidate_packet)
    return packet, metrics


def _bounded_prompt(payload: dict[str, Any], max_chars: int) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str)
    if len(encoded) <= max_chars:
        return encoded
    compact = {
        "context_truncated": True,
        "context_hash": _sha256(encoded),
        "bounded_context": encoded[: max(1000, max_chars - 300)],
    }
    result = json.dumps(compact, sort_keys=True)
    while len(result) > max_chars and len(compact["bounded_context"]) > 1000:
        compact["bounded_context"] = compact["bounded_context"][:-500]
        result = json.dumps(compact, sort_keys=True)
    return result


Validator = Callable[[Any, dict[str, Any], dict[str, Any]], tuple[dict[str, Any], list[str]]]


def _refresh_generation_summary(state: dict[str, Any]) -> None:
    generation = state.setdefault("llm_generation", {})
    phases = generation.get("phases") if isinstance(generation.get("phases"), dict) else {}
    records = [item for item in phases.values() if isinstance(item, dict)]
    statuses = {str(item.get("status") or "") for item in records}
    if "completed_with_fallback" in statuses:
        status = "completed_with_fallback"
    elif records and statuses <= {"skipped_quick_test"}:
        status = "skipped_quick_test"
    elif records:
        status = "completed"
    else:
        status = "not_started"
    generation.update(
        {
            "schema_version": "mn.blueprint.purchasing_manager.llm_generation.v1",
            "status": status,
            "max_calls_per_run": generation.get("max_calls_per_run") or MAX_LLM_CALLS,
            "calls_made": sum(int(item.get("calls") or 0) for item in records),
            "raw_prompt_persisted": False,
            "phases": phases,
        }
    )
    providers = {str(item.get("provider") or "unknown") for item in records}
    models = {str(item.get("model") or "unknown") for item in records}
    state["llm_usage"] = {
        "provider": next(iter(providers)) if len(providers) == 1 else "multiple",
        "model": next(iter(models)) if len(models) == 1 else "multiple",
        "calls": generation["calls_made"],
        "fallback_calls": sum(item.get("status") == "completed_with_fallback" for item in records),
        "input_tokens": sum(int(item.get("input_tokens") or 0) for item in records),
        "output_tokens": sum(int(item.get("output_tokens") or 0) for item in records),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in records),
        "estimated_tokens": sum(int(item.get("estimated_tokens") or 0) for item in records),
    }


def generate_structured_analysis(
    *,
    state: dict[str, Any],
    config: dict[str, Any],
    agent_id: str,
    prompt_name: str,
    payload: dict[str, Any],
    fallback: dict[str, Any],
    validator: Validator,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    settings = analysis_settings(config)
    normalized_fallback, _fallback_errors = validator(fallback, fallback, settings)
    generation = state.setdefault(
        "llm_generation",
        {
            "schema_version": "mn.blueprint.purchasing_manager.llm_generation.v1",
            "status": "not_started",
            "max_calls_per_run": settings["max_calls_per_run"],
            "calls_made": 0,
            "raw_prompt_persisted": False,
            "phases": {},
        },
    )
    phases = generation.setdefault("phases", {})
    cached_results = state.setdefault("_llm_analysis_results", {})
    if agent_id in phases and isinstance(cached_results.get(agent_id), dict):
        return deepcopy(cached_results[agent_id])
    if not llm_agent_selected(config, agent_id):
        phases[agent_id] = {
            "status": "not_selected",
            "calls": 0,
            "validation_status": "deterministic_fallback",
            "fallback_reason": "agent_not_selected",
            "raw_prompt_persisted": False,
        }
        cached_results[agent_id] = deepcopy(normalized_fallback)
        _refresh_generation_summary(state)
        return deepcopy(normalized_fallback)
    if int(generation.get("calls_made") or 0) >= settings["max_calls_per_run"]:
        warning = {
            "kind": "llm_analysis",
            "status": "llm_analysis_fallback",
            "agent_id": agent_id,
            "message": "The LLM call budget was exhausted; deterministic narrative was preserved.",
        }
        state.setdefault("llm_warnings", []).append(warning)
        phases[agent_id] = {
            "status": "completed_with_fallback",
            "calls": 0,
            "validation_status": "deterministic_fallback",
            "fallback_reason": "call_budget_exhausted",
            "raw_prompt_persisted": False,
        }
        cached_results[agent_id] = deepcopy(normalized_fallback)
        _refresh_generation_summary(state)
        return deepcopy(normalized_fallback)

    prompt = load_prompt(prompt_name)
    user_prompt = _bounded_prompt(payload, settings["max_context_chars"])
    prompt_hash = _sha256(f"{prompt}\n{user_prompt}")
    llm = purchase_llm(config, llm_client)
    before = llm_usage(llm)
    error = ""
    raw: Any = fallback
    try:
        raw = llm.generate_json(
            system_prompt=prompt,
            user_prompt=user_prompt,
            fallback=normalized_fallback,
        )
    except Exception as exc:  # model availability is optional for this blueprint
        error = str(exc)
        raw = fallback
    after = llm_usage(llm)
    normalized, validation_errors = validator(raw, fallback, settings)
    fallback_delta = max(
        0, int(after.get("fallback_calls") or 0) - int(before.get("fallback_calls") or 0)
    )
    skipped_quick = (
        not error
        and not validation_errors
        and quick_test_enabled(config)
        and str(after.get("provider") or "") == "fake"
        and normalized == normalized_fallback
    )
    used_fallback = bool(error or validation_errors or (fallback_delta and not skipped_quick))
    status = "skipped_quick_test" if skipped_quick else "completed_with_fallback" if used_fallback else "completed"
    reason = ""
    if error:
        reason = "llm_call_failed"
    elif validation_errors:
        reason = "validation_failed"
    elif fallback_delta:
        reason = "provider_fallback"
    elif skipped_quick:
        reason = "quick_test_deterministic"
    phase = {
        "status": status,
        "provider": after.get("provider") or "unknown",
        "model": after.get("model") or "unknown",
        "calls": max(1, int(after.get("calls") or 0) - int(before.get("calls") or 0)),
        "input_tokens": max(0, int(after.get("input_tokens") or 0) - int(before.get("input_tokens") or 0)),
        "output_tokens": max(0, int(after.get("output_tokens") or 0) - int(before.get("output_tokens") or 0)),
        "total_tokens": max(0, int(after.get("total_tokens") or 0) - int(before.get("total_tokens") or 0)),
        "estimated_tokens": max(0, int(after.get("estimated_tokens") or 0) - int(before.get("estimated_tokens") or 0)),
        "prompt_hash": prompt_hash,
        "prompt_chars": len(user_prompt),
        "validation_status": "valid" if not validation_errors else "fallback_applied",
        "validation_errors": validation_errors[: settings["max_list_items"]],
        "fallback_reason": reason,
        "raw_prompt_persisted": False,
    }
    if error:
        phase["error"] = error[:500]
    phases[agent_id] = phase
    if status == "completed_with_fallback":
        state.setdefault("llm_warnings", []).append(
            {
                "kind": "llm_analysis",
                "status": "llm_analysis_fallback",
                "agent_id": agent_id,
                "message": "LLM analysis was unavailable or invalid; deterministic narrative was preserved.",
                "fallback_reason": reason,
                "validation_errors": validation_errors[: settings["max_list_items"]],
                **({"error": error[:500]} if error else {}),
            }
        )
    cached_results[agent_id] = deepcopy(normalized)
    _refresh_generation_summary(state)
    return normalized


def validate_tco_analysis(
    response: Any, fallback: dict[str, Any], settings: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(response, dict):
        errors.append("response: expected object")
    value = response if isinstance(response, dict) else {}
    allowed_numbers = set(fallback.get("_allowed_numbers") or [])
    candidate_ids = set(fallback.get("_candidate_ids") or [])
    metric_refs = set(fallback.get("_metric_refs") or [])
    source_refs = set(fallback.get("_source_refs") or [])
    clean = {
        "summary": _text(value.get("summary"), fallback["summary"], field="summary", allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"]),
        "primary_cost_drivers": [],
        "scenario_insights": [],
        "assumption_sensitivities": [],
        "acquisition_method_tradeoffs": [],
        "evidence_gaps": _string_list(value.get("evidence_gaps"), fallback["evidence_gaps"], field="evidence_gaps", allowed_numbers=allowed_numbers, errors=errors, max_items=settings["max_list_items"], max_chars=settings["max_text_chars"]),
        "source_refs": _reference_list(value.get("source_refs"), fallback["source_refs"], field="source_refs", allowed=source_refs, errors=errors, max_items=settings["max_list_items"]),
    }
    list_contracts = (
        ("primary_cost_drivers", ("explanation",)),
        ("scenario_insights", ("scenario_name", "interpretation")),
        ("assumption_sensitivities", ("assumption_key", "direction", "why", "verification_needed")),
        ("acquisition_method_tradeoffs", ("method", "status", "interpretation")),
    )
    for field, text_fields in list_contracts:
        raw_items = value.get(field) if isinstance(value.get(field), list) else fallback[field]
        fallback_items = fallback[field]
        for index, item in enumerate(raw_items[: settings["max_list_items"]]):
            if not isinstance(item, dict):
                errors.append(f"{field}[{index}]: expected object")
                continue
            candidate_id = str(item.get("candidate_id") or "")
            if field != "assumption_sensitivities":
                if candidate_id and candidate_id not in candidate_ids:
                    errors.append(f"{field}[{index}]: unknown candidate_id")
                    continue
            metric_values = item.get("metric_refs") or []
            valid_metric_values = _reference_list(metric_values, [], field=f"{field}[{index}].metric_refs", allowed=metric_refs, errors=errors, max_items=settings["max_list_items"])
            base = fallback_items[index] if index < len(fallback_items) and isinstance(fallback_items[index], dict) else {}
            normalized = {key: item.get(key) for key in item if key in {*text_fields, "candidate_id", "metric_refs"}}
            if field != "assumption_sensitivities":
                normalized["candidate_id"] = candidate_id
            else:
                normalized.pop("candidate_id", None)
            normalized["metric_refs"] = valid_metric_values
            for text_field in text_fields:
                normalized[text_field] = _text(item.get(text_field), str(base.get(text_field) or ""), field=f"{field}[{index}].{text_field}", allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"])
            clean[field].append(normalized)
        if not clean[field]:
            clean[field] = deepcopy(fallback_items)
    return clean, errors


def validate_risk_analysis(
    response: Any, fallback: dict[str, Any], settings: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(response, dict):
        errors.append("response: expected object")
    value = response if isinstance(response, dict) else {}
    allowed_numbers = set(fallback.get("_allowed_numbers") or [])
    candidate_ids = set(fallback.get("_candidate_ids") or [])
    source_refs = set(fallback.get("_source_refs") or [])
    posture = str(value.get("overall_posture") or fallback["overall_posture"]).lower()
    if posture not in {"low", "moderate", "high", "indeterminate"}:
        errors.append("overall_posture: invalid enum")
        posture = fallback["overall_posture"]
    clean = {
        "overall_posture": posture,
        "material_risks": [],
        "deal_breakers": _string_list(value.get("deal_breakers"), fallback["deal_breakers"], field="deal_breakers", allowed_numbers=allowed_numbers, errors=errors, max_items=settings["max_list_items"], max_chars=settings["max_text_chars"]),
        "negotiation_points": _string_list(value.get("negotiation_points"), fallback["negotiation_points"], field="negotiation_points", allowed_numbers=allowed_numbers, errors=errors, max_items=settings["max_list_items"], max_chars=settings["max_text_chars"]),
        "verification_plan": _string_list(value.get("verification_plan"), fallback["verification_plan"], field="verification_plan", allowed_numbers=allowed_numbers, errors=errors, max_items=settings["max_list_items"], max_chars=settings["max_text_chars"]),
        "source_refs": _reference_list(value.get("source_refs"), fallback["source_refs"], field="source_refs", allowed=source_refs, errors=errors, max_items=settings["max_list_items"]),
    }
    severities = {"low", "moderate", "high", "critical", "indeterminate"}
    raw_risks = value.get("material_risks") if isinstance(value.get("material_risks"), list) else fallback["material_risks"]
    for index, item in enumerate(raw_risks[: settings["max_list_items"]]):
        if not isinstance(item, dict):
            errors.append(f"material_risks[{index}]: expected object")
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id and candidate_id not in candidate_ids:
            errors.append(f"material_risks[{index}]: unknown candidate_id")
            continue
        severity = str(item.get("severity") or "indeterminate").lower()
        if severity not in severities:
            errors.append(f"material_risks[{index}]: invalid severity")
            severity = "indeterminate"
        base = fallback["material_risks"][index] if index < len(fallback["material_risks"]) else {}
        clean["material_risks"].append(
            {
                "candidate_id": candidate_id,
                "category": _text(item.get("category"), str(base.get("category") or "procurement"), field=f"material_risks[{index}].category", allowed_numbers=allowed_numbers, errors=errors, max_chars=120),
                "severity": severity,
                "reason": _text(item.get("reason"), str(base.get("reason") or "Verification remains incomplete."), field=f"material_risks[{index}].reason", allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"]),
                "mitigation": _text(item.get("mitigation"), str(base.get("mitigation") or "Verify before approval."), field=f"material_risks[{index}].mitigation", allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"]),
                "owner_role": _text(item.get("owner_role"), str(base.get("owner_role") or "Procurement owner"), field=f"material_risks[{index}].owner_role", allowed_numbers=allowed_numbers, errors=errors, max_chars=160),
                "blocks_commitment": item.get("blocks_commitment")
                if isinstance(item.get("blocks_commitment"), bool)
                else bool(base.get("blocks_commitment", True)),
                "evidence_refs": _reference_list(item.get("evidence_refs"), list(base.get("evidence_refs") or []), field=f"material_risks[{index}].evidence_refs", allowed=source_refs, errors=errors, max_items=settings["max_list_items"]),
            }
        )
    if not clean["material_risks"]:
        clean["material_risks"] = deepcopy(fallback["material_risks"])
    return clean, errors


def validate_decision_analysis(
    response: Any, fallback: dict[str, Any], settings: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(response, dict):
        errors.append("response: expected object")
    value = response if isinstance(response, dict) else {}
    allowed_numbers = set(fallback.get("_allowed_numbers") or [])
    candidate_ids = set(fallback.get("_candidate_ids") or [])
    source_refs = set(fallback.get("_source_refs") or [])
    clean = {
        key: _text(value.get(key), fallback[key], field=key, allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"])
        for key in (
            "why_preferred",
            "strongest_reason_to_proceed",
            "strongest_reason_to_wait",
            "confidence_explanation",
        )
    }
    clean["approval_conditions"] = _string_list(value.get("approval_conditions"), fallback["approval_conditions"], field="approval_conditions", allowed_numbers=allowed_numbers, errors=errors, max_items=settings["max_list_items"], max_chars=settings["max_text_chars"])
    clean["source_refs"] = _reference_list(value.get("source_refs"), fallback["source_refs"], field="source_refs", allowed=source_refs, errors=errors, max_items=settings["max_list_items"])
    clean["why_not_alternatives"] = []
    raw_alternatives = value.get("why_not_alternatives") if isinstance(value.get("why_not_alternatives"), list) else fallback["why_not_alternatives"]
    for index, item in enumerate(raw_alternatives[: settings["max_list_items"]]):
        if not isinstance(item, dict):
            errors.append(f"why_not_alternatives[{index}]: expected object")
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id not in candidate_ids:
            errors.append(f"why_not_alternatives[{index}]: unknown candidate_id")
            continue
        base = fallback["why_not_alternatives"][index] if index < len(fallback["why_not_alternatives"]) else {}
        clean["why_not_alternatives"].append(
            {
                "candidate_id": candidate_id,
                "explanation": _text(item.get("explanation"), str(base.get("explanation") or "The deterministic ranking placed this option below the preferred eligible option."), field=f"why_not_alternatives[{index}].explanation", allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"]),
            }
        )
    if not clean["why_not_alternatives"]:
        clean["why_not_alternatives"] = deepcopy(fallback["why_not_alternatives"])
    return clean, errors


def validate_report_narrative(
    response: Any, fallback: dict[str, Any], settings: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(response, dict):
        errors.append("response: expected object")
    value = response if isinstance(response, dict) else {}
    allowed_numbers = set(fallback.get("_allowed_numbers") or [])
    candidate_ids = set(fallback.get("_candidate_ids") or [])
    source_refs = set(fallback.get("_source_refs") or [])
    clean = {
        key: _text(value.get(key), fallback[key], field=key, allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"])
        for key in (
            "executive_summary",
            "decision_rationale",
            "financial_interpretation",
            "risk_interpretation",
        )
    }
    for key in ("negotiation_points", "approval_conditions"):
        clean[key] = _string_list(value.get(key), fallback[key], field=key, allowed_numbers=allowed_numbers, errors=errors, max_items=settings["max_list_items"], max_chars=settings["max_text_chars"])
    clean["source_refs"] = _reference_list(value.get("source_refs"), fallback["source_refs"], field="source_refs", allowed=source_refs, errors=errors, max_items=settings["max_list_items"])
    clean["alternative_tradeoffs"] = []
    raw_alternatives = value.get("alternative_tradeoffs") if isinstance(value.get("alternative_tradeoffs"), list) else fallback["alternative_tradeoffs"]
    for index, item in enumerate(raw_alternatives[: settings["max_list_items"]]):
        if not isinstance(item, dict):
            errors.append(f"alternative_tradeoffs[{index}]: expected object")
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id not in candidate_ids:
            errors.append(f"alternative_tradeoffs[{index}]: unknown candidate_id")
            continue
        base = fallback["alternative_tradeoffs"][index] if index < len(fallback["alternative_tradeoffs"]) else {}
        clean["alternative_tradeoffs"].append(
            {
                "candidate_id": candidate_id,
                "interpretation": _text(item.get("interpretation"), str(base.get("interpretation") or "See the deterministic candidate comparison."), field=f"alternative_tradeoffs[{index}].interpretation", allowed_numbers=allowed_numbers, errors=errors, max_chars=settings["max_text_chars"]),
            }
        )
    if not clean["alternative_tradeoffs"]:
        clean["alternative_tradeoffs"] = deepcopy(fallback["alternative_tradeoffs"])
    return clean, errors


def analysis_validation_context(
    state: dict[str, Any], payload: dict[str, Any]
) -> dict[str, list[str]]:
    comparisons = state.get("candidate_comparisons") or []
    return {
        "_allowed_numbers": sorted(_canonical_numbers(payload)),
        "_candidate_ids": [
            str(item.get("candidate_id"))
            for item in comparisons
            if isinstance(item, dict) and item.get("candidate_id")
        ],
        "_source_refs": sorted(known_source_refs(state)),
    }


__all__ = [
    "MAX_LLM_CALLS",
    "SELECTED_AGENT_IDS",
    "analysis_settings",
    "analysis_validation_context",
    "candidate_analysis_packet",
    "generate_structured_analysis",
    "known_source_refs",
    "llm_agent_selected",
    "validate_decision_analysis",
    "validate_report_narrative",
    "validate_risk_analysis",
    "validate_tco_analysis",
]
