"""Required, grounded local-model analysis with durable metadata-only provenance."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mn_blueprint_support import get_actor_llm_client, llm_usage
from mn_sdk.blueprint_support import (
    ActionBudget,
    BudgetedLlmClient,
    build_llm_call_limiter,
    redact_observation_value,
)
from mn_sdk.blueprint_support.utils import utc_now_iso
from mn_sdk.blueprint_support.workflow_state import WorkflowStateStore

from .state import write_state

STAGES = (
    "source_intake",
    "component_mapping",
    "cross_cutting_mapping",
    "finding_synthesis",
    "adversarial_review",
    "prompt_authoring",
    "report_synthesis",
    "final_audit",
)
STAGE_ACTORS = {
    "source_intake": "source_intake_analyst",
    "component_mapping": "codebase_mapper",
    "cross_cutting_mapping": "codebase_mapper",
    "finding_synthesis": "architecture_reviewer",
    "adversarial_review": "architecture_reviewer",
    "prompt_authoring": "improvement_prompt_author",
    "report_synthesis": "architecture_report_writer",
    "final_audit": "architecture_advice_auditor",
}
_PROMPT_FILES = {stage: f"{stage.replace('_', '-')}-system.md" for stage in STAGES}
_LEDGER_FILE = "software_architecture_advisor_llm_action_ledger.json"
_TRACE_FILE = "llm_trace.jsonl"
_LIVE_PROVIDERS = {
    "docker_model_runner", "litellm", "litellm_proxy", "openai_compatible",
    "ollama", "local_openai_compatible", "live-test", "scripted-live",
}
_METADATA_NAMES = {
    "agents.md", "cargo.toml", "docker-compose.yml", "docker-compose.yaml",
    "dockerfile", "go.mod", "makefile", "package.json", "pom.xml",
    "pyproject.toml", "readme", "readme.md", "requirements.txt", "tsconfig.json",
}
_SAFE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c",
    ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".kts",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".gradle",
    ".properties", ".lock", ".sh", ".sql", ".tf", ".hcl", ".graphql",
}
_SENSITIVE_MARKERS = ("secret", "credential", "password", "private_key", ".pem", ".p12", ".env")

_STAGE_OUTPUT_CONTRACTS: dict[str, dict[str, Any]] = {
    "source_intake": {
        "required_fields": {
            "summary": "non-empty string",
            "investigation_priorities": "non-empty array of priority objects",
            "entrypoint_hypotheses": "array of entrypoint objects; use [] when none are supported",
            "unknowns": "array of strings",
        },
        "item_contracts": {
            "investigation_priorities[]": {
                "question": "non-empty string",
                "rationale": "non-empty string",
                "evidence_targets": "array of strings",
                "path_refs": "array containing only exact paths from bounded_context.files",
            },
            "entrypoint_hypotheses[]": {
                "path": "one exact path from bounded_context.files",
                "reason": "non-empty string",
            },
        },
    },
    "component_mapping": {
        "required_fields": {
            "summary": "non-empty string",
            "components": "non-empty array of component objects",
            "entrypoints": "array of entrypoint objects",
            "dependency_directions": "array of dependency objects; use [] when none are supported",
            "unknowns": "array of strings",
        },
        "item_contracts": {
            "components[]": {"component_id": "string", "name": "string", "responsibility": "string", "paths": "non-empty exact-path array", "fact_ids": "exact fact-ID array"},
            "entrypoints[]": {"path": "one exact path", "role": "string", "fact_ids": "exact fact-ID array"},
            "dependency_directions[]": {"from_component": "string", "to_component": "string", "relationship": "string", "paths": "non-empty exact-path array", "fact_ids": "exact fact-ID array"},
        },
    },
    "cross_cutting_mapping": {
        "required_fields": {
            "summary": "non-empty string",
            "flows": "array of analysis objects",
            "state_ownership": "array of analysis objects",
            "trust_boundaries": "array of analysis objects",
            "deployment_interactions": "array of analysis objects",
            "test_observations": "array of analysis objects",
            "unknowns": "array of strings",
        },
        "item_contracts": {
            "each analysis object": {"name": "string", "analysis": "string", "confidence": "low|medium|high", "paths": "exact-path array", "fact_ids": "non-empty exact fact-ID array"},
        },
    },
    "finding_synthesis": {
        "required_fields": {
            "summary": "non-empty string",
            "deterministic_finding_rationales": "array keyed by supplied deterministic finding_id; omitted or unsafe fields are restored from deterministic evidence",
            "grounded_findings": "array of new grounded-finding objects; use [] instead of weak or unsupported candidates",
        },
        "item_contracts": {
            "deterministic_finding_rationales[]": {"finding_id": "exact supplied deterministic finding_id", "rationale": "string", "tradeoffs": "array of strings", "migration_risks": "array of strings", "fact_ids": "non-empty exact fact-ID array"},
            "grounded_findings[]": {"finding_id": "new unique string", "title": "string", "category": "string", "summary": "string", "interpretation": "string", "why_it_matters": "string", "recommendation": "string", "rollback_considerations": "string", "severity": "low|medium|high|critical", "fact_ids": "non-empty exact fact-ID array", "paths": "non-empty exact-path array", "alternative_options": "array of at least two option objects", "counter_evidence_considered": "array of strings", "migration_risk": "string", "migration_sequence": "array of strings", "test_strategy": "array of strings", "stop_conditions": "array of strings"},
            "alternative_options[]": {"option_id": "string", "title": "string", "direction": "string", "tradeoffs": "string", "recommended": "boolean"},
        },
    },
    "adversarial_review": {
        "required_fields": {"summary": "non-empty string", "finding_reviews": "array with exactly one object for every supplied candidate finding_id", "required_human_checks": "array of strings"},
        "item_contracts": {
            "finding_reviews[]": {"finding_id": "exact supplied candidate finding_id", "verdict": "retain|revise|downgrade|reject", "revised_severity": "low|medium|high|critical", "revised_confidence": "low|medium|high", "rationale": "string", "fact_ids": "non-empty exact fact-ID array", "missing_evidence": "array of strings"},
        },
    },
    "prompt_authoring": {
        "required_fields": {"summary": "non-empty string", "prompts": "array with exactly one object for every supplied surviving finding_id"},
        "item_contracts": {
            "prompts[]": {"finding_id": "exact supplied finding_id", "objective": "string", "architecture_intent": "string", "option_guidance": "array of at least two strings", "implementation_steps": "non-empty string array", "tests": "non-empty string array", "rollback": "string", "stop_conditions": "non-empty string array", "fact_ids": "non-empty exact fact-ID array"},
        },
    },
    "report_synthesis": {
        "required_fields": {"sections": "object containing the five named section objects; unsafe or omitted section fields are restored from the deterministic report scaffold", "coverage": "array containing the five section names"},
        "item_contracts": {
            "sections": "exact keys: executive_summary, system_reconstruction, cross_cutting_analysis, finding_rationale, migration_strategy",
            "each section": {"text": "non-empty analytical prose with no numeric claims", "fact_ids": "non-empty exact fact-ID array"},
        },
    },
    "final_audit": {
        "required_fields": {"verdict": "approve|reject", "summary": "non-empty string", "checks": "array containing exactly the five named check objects", "rejected_claims": "array of strings", "required_revisions": "array of strings"},
        "item_contracts": {
            "checks[]": {"name": "one exact required check name", "status": "approve|reject", "rationale": "string", "fact_ids": "exact fact-ID array"},
            "required check names": "claims_are_fact_grounded, metrics_are_deterministic, adversarial_dispositions_are_complete, prompts_are_safe_and_reversible, report_coverage_is_complete",
            "rejected_claims[]": "when rejecting a package whose deterministic gate passed, quote an exact concrete claim from bounded_context",
        },
    },
}

_STAGE_RESPONSE_LIMITS: dict[str, dict[str, Any]] = {
    "source_intake": {
        "maximum_total_json_characters": 5_000,
        "maximum_items": {
            "investigation_priorities": 3,
            "entrypoint_hypotheses": 3,
            "unknowns": 3,
            "path_refs_per_item": 3,
        },
        "maximum_prose_characters_per_field": 180,
    },
    "component_mapping": {
        "maximum_total_json_characters": 6_000,
        "maximum_items": {
            "components": 5,
            "entrypoints": 4,
            "dependency_directions": 5,
            "unknowns": 3,
            "paths_or_fact_ids_per_item": 3,
        },
        "maximum_prose_characters_per_field": 140,
    },
    "cross_cutting_mapping": {
        "maximum_total_json_characters": 6_000,
        "maximum_items": {
            "each_analysis_array": 2,
            "unknowns": 3,
            "paths_or_fact_ids_per_item": 3,
        },
        "maximum_prose_characters_per_field": 140,
    },
    "finding_synthesis": {
        "maximum_total_json_characters": 6_500,
        "maximum_items": {
            "deterministic_finding_rationales": "exactly one per supplied finding_id",
            "tradeoffs_or_migration_risks_per_item": 1,
            "grounded_findings": 0,
        },
        "maximum_prose_characters_per_field": 120,
    },
    "adversarial_review": {
        "maximum_total_json_characters": 6_500,
        "maximum_items": {
            "finding_reviews": "exactly one per supplied finding_id",
            "missing_evidence_per_item": 1,
            "required_human_checks": 2,
        },
        "maximum_prose_characters_per_field": 120,
    },
    "prompt_authoring": {
        "maximum_total_json_characters": 7_000,
        "maximum_items": {
            "prompts": "exactly one per supplied finding_id",
            "option_guidance_per_item": 2,
            "implementation_steps_per_item": 2,
            "tests_per_item": 2,
            "stop_conditions_per_item": 2,
        },
        "maximum_prose_characters_per_field": 120,
    },
    "report_synthesis": {
        "maximum_total_json_characters": 6_500,
        "maximum_items": {
            "sections": "exactly the five required sections",
            "fact_ids_per_section": 4,
        },
        "maximum_words_per_section": 80,
    },
    "final_audit": {
        "maximum_total_json_characters": 5_000,
        "maximum_items": {
            "checks": "exactly the five required checks",
            "fact_ids_per_check": 3,
            "rejected_claims": 2,
            "required_revisions": 2,
        },
        "maximum_prose_characters_per_field": 120,
    },
}

StageValidator = Callable[[dict[str, Any]], dict[str, Any] | None]


def fake_mode(config: dict[str, Any]) -> bool:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    env_fake = str(os.environ.get("MN_BLUEPRINT_QUICK_TEST") or "").lower() in {"1", "true", "yes", "on"}
    return str(llm.get("mode") or "live").lower() in {"fake", "mock", "test", "deterministic"} or bool(execution.get("quick_test")) or env_fake


def run_model_stage(
    ctx: dict[str, Any],
    state: dict[str, Any],
    *,
    stage: str,
    task: str,
    context: dict[str, Any],
    fallback: dict[str, Any],
    validator: StageValidator,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """Run one required model action, fail closed live, and persist no raw prompt."""
    if stage not in STAGES:
        raise ValueError(f"Unknown architecture-analysis stage: {stage}")
    analysis = _analysis_state(state)
    prior_record = (analysis.get("stages") or {}).get(stage)
    if isinstance(prior_record, dict) and prior_record.get("status") in {"completed", "completed_fake"}:
        return dict(prior_record.get("output") or {})
    stage_index = STAGES.index(stage)
    missing = [name for name in STAGES[:stage_index] if name not in (analysis.get("stages") or {})]
    if missing:
        raise ValueError(f"LLM stage {stage} cannot run before: {', '.join(missing)}")

    config = ctx.get("config") or {}
    quick = fake_mode(config)
    require_live = bool((config.get("llm") or {}).get("require_live", True)) and not quick
    system_prompt = _load_prompt(ctx, stage)
    context, user_prompt, prompt_budget = _prepare_budgeted_prompt(
        config,
        stage=stage,
        task=task,
        system_prompt=system_prompt,
        context=context,
    )
    prompt_hash = hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode()).hexdigest()
    budget = _load_budget(ctx, config)
    limiter = build_llm_call_limiter(config, fake_mode=quick)
    raw_llm = get_actor_llm_client(config, llm_client)
    client = BudgetedLlmClient(
        raw_llm,
        budget,
        require_live=require_live,
        limiter=limiter,
        run_dir=Path(ctx["run_dir"]),
        observation_writer=_append_observation,
        resource_writer=_append_resource,
        provider_live_check=lambda provider: provider.lower() in _LIVE_PROVIDERS or (provider and provider.lower() not in {"fake", "mock", "fallback", "unavailable", "budget_exhausted", "llm_unavailable"}),
        action_type="required_architecture_llm_pass",
        tool_name="local_default_model",
        operation="software_architecture_advisor.generate_json",
        heartbeat_seconds=10.0,
    )
    before = llm_usage(raw_llm)
    started = time.monotonic()
    record: dict[str, Any] = {
        "stage": stage,
        "stage_index": stage_index + 1,
        "actor": STAGE_ACTORS[stage],
        "status": "running",
        "prompt_hash": prompt_hash,
        "prompt_chars": len(user_prompt),
        **prompt_budget,
        "context_kind": str(context.get("packet_kind") or "structured_evidence"),
        "context_item_count": _context_item_count(context),
        "raw_prompt_persisted": False,
        "raw_source_persisted": False,
        "full_response_persisted_in_trace": False,
        "started_at": utc_now_iso(),
    }
    try:
        response = client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
            stage=stage,
            metadata={
                "actor": STAGE_ACTORS[stage],
                "stage_index": stage_index + 1,
                "prompt_hash": prompt_hash,
                "context_kind": record["context_kind"],
                "context_item_count": record["context_item_count"],
            },
            validator=validator,
            validation_retries=max(0, int((config.get("llm_analysis") or {}).get("validation_retries") or 1)),
        )
        validated = validator(response)
        if validated is None:
            raise ValueError(f"Stage {stage} returned invalid structured output after validation retries.")
        after = llm_usage(raw_llm)
        usage = _usage_delta(before, after)
        last_usage = after.get("last_usage") if isinstance(after.get("last_usage"), dict) else {}
        fallback_used = bool(usage["fallback_calls"] or last_usage.get("fallback"))
        provider_responses = int(last_usage.get("provider_response_count") or 0)
        if require_live and fallback_used:
            raise RuntimeError(f"Required live LLM stage {stage} used a fallback response.")
        if require_live and provider_responses < 1:
            raise RuntimeError(f"Required live LLM stage {stage} recorded no real provider response.")
        if require_live and int(usage["input_tokens"]) + int(usage["output_tokens"]) <= 0:
            raise RuntimeError(f"Required live LLM stage {stage} recorded no provider token usage.")
        record.update({
            "status": "completed_fake" if quick else "completed",
            "provider": str(after.get("provider") or getattr(raw_llm, "provider", "unknown")),
            "model": str(after.get("model") or getattr(raw_llm, "model", "unknown")),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            **usage,
            "provider_response_count": provider_responses,
            "validation_retries": int(last_usage.get("structured_output_retries") or 0),
            "fallback": fallback_used,
            "output": validated,
            "completed_at": utc_now_iso(),
        })
        analysis.setdefault("stages", {})[stage] = record
        _refresh_analysis(state)
        _persist_budget(ctx, budget)
        write_state(ctx, state)
        _append_stage_trace(ctx, record)
        return validated
    except Exception as exc:
        after = llm_usage(raw_llm)
        last_usage = after.get("last_usage") if isinstance(after.get("last_usage"), dict) else {}
        record.update({
            "status": "failed",
            "provider": str(after.get("provider") or getattr(raw_llm, "provider", "unknown")),
            "model": str(after.get("model") or getattr(raw_llm, "model", "unknown")),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            **_usage_delta(before, after),
            "provider_response_count": int(last_usage.get("provider_response_count") or 0),
            "validation_retries": int(last_usage.get("structured_output_retries") or 0),
            "fallback": bool(last_usage.get("fallback")),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "completed_at": utc_now_iso(),
        })
        analysis.setdefault("stages", {})[stage] = record
        _refresh_analysis(state)
        _persist_budget(ctx, budget)
        write_state(ctx, state)
        _append_stage_trace(ctx, record)
        raise


def build_source_packet(ctx: dict[str, Any], state: dict[str, Any], *, stage: str) -> dict[str, Any]:
    """Build a stage-specific source packet that is never returned or persisted."""
    root = Path((state.get("source") or {}).get("root") or "").resolve()
    if not root.is_dir():
        raise ValueError("The staged source root is unavailable for model analysis.")
    config = ctx.get("config") or {}
    packet_config = config.get("source_packets") if isinstance(config.get("source_packets"), dict) else {}
    max_chars = min(90_000, max(8_000, int(packet_config.get("max_chars") or 72_000)))
    max_files = min(24, max(4, int(packet_config.get("max_files") or 14)))
    per_file = min(8_000, max(800, int(packet_config.get("max_chars_per_file") or 4_000)))
    selected = _selected_paths(root, state, stage=stage, max_files=max_files)
    excerpts: list[dict[str, Any]] = []
    used = 0
    for rel in selected:
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file() or _sensitive_path(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = text[: min(per_file, max_chars - used)]
        if not excerpt:
            continue
        excerpts.append({
            "path": rel,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "line_count": text.count("\n") + 1,
            "excerpt": excerpt,
            "excerpt_truncated": len(excerpt) < len(text),
        })
        used += len(excerpt)
        if used >= max_chars:
            break
    packet: dict[str, Any] = {
        "packet_kind": f"bounded_{stage}_source_packet",
        "repository_name": root.name,
        "analysis_focus": ((state.get("inputs") or {}).get("analysis_focus") or []),
        "files": excerpts,
        "packet_limits": {"max_chars": max_chars, "max_files": max_files, "max_chars_per_file": per_file},
        "source_bodies_must_not_be_persisted": True,
    }
    if stage != "source_intake":
        packet.update({
            "repository_profile": state.get("repository_profile") or {},
            "deterministic_reconstruction": state.get("deterministic_reconstruction") or {},
            "metrics": state.get("metrics") or {},
            "facts": ((state.get("architecture_facts") or {}).get("facts") or [])[:180],
            "state_model": state.get("state_model") or {},
            "trust_model": state.get("trust_model") or {},
            "test_architecture": state.get("test_architecture") or {},
            "deployment_model": state.get("deployment_model") or {},
        })
    return packet


def _prepare_budgeted_prompt(
    config: dict[str, Any],
    *,
    stage: str,
    task: str,
    system_prompt: str,
    context: dict[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Fit a complete serialized prompt inside its model profile's input budget."""
    context_size, completion_reserve, safety_margin, bytes_per_token = _stage_token_budget(config, stage)
    input_budget = context_size - completion_reserve - safety_margin
    if input_budget <= 0:
        raise ValueError(
            f"Invalid LLM token budget for {stage}: context_size={context_size}, "
            f"completion_reserve={completion_reserve}, safety_margin={safety_margin}."
        )

    def render(candidate: dict[str, Any]) -> tuple[str, int]:
        user_prompt = json.dumps(_user_payload(stage, task, candidate), sort_keys=True, default=str)
        estimated = _estimate_tokens(system_prompt, bytes_per_token) + _estimate_tokens(user_prompt, bytes_per_token)
        return user_prompt, estimated

    bounded_context = copy.deepcopy(context)
    user_prompt, estimated = render(bounded_context)
    original_estimated = estimated
    compacted = False

    if estimated > input_budget and str(bounded_context.get("packet_kind") or "").startswith("bounded_"):
        bounded_context = _compact_source_packet_to_budget(
            bounded_context,
            input_budget=input_budget,
            render=render,
        )
        user_prompt, estimated = render(bounded_context)
        compacted = True

    if estimated > input_budget and bounded_context.get("packet_kind") == "validated_architecture_evidence":
        bounded_context = _compact_structured_packet_to_budget(
            bounded_context,
            input_budget=input_budget,
            render=render,
        )
        user_prompt, estimated = render(bounded_context)
        compacted = True

    if estimated > input_budget:
        raise ValueError(
            f"Prompt for {stage} requires an estimated {estimated} input tokens but its budget is "
            f"{input_budget} ({context_size} context - {completion_reserve} completion - "
            f"{safety_margin} safety)."
        )

    return bounded_context, user_prompt, {
        "estimated_input_tokens": estimated,
        "original_estimated_input_tokens": original_estimated,
        "input_token_budget": input_budget,
        "context_window_tokens": context_size,
        "reserved_completion_tokens": completion_reserve,
        "token_safety_margin": safety_margin,
        "prompt_compacted": compacted,
    }


def _user_payload(stage: str, task: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": stage,
        "task": task,
        "bounded_context": context,
        "required_output_contract": _STAGE_OUTPUT_CONTRACTS[stage],
        "response_limits": _STAGE_RESPONSE_LIMITS[stage],
        "structured_output_rules": [
            "Return exactly one JSON object with every required top-level field.",
            "Arrays declared as object arrays may contain only objects, never prose strings.",
            "Use an empty array only where the contract explicitly permits it.",
            "Copy cited identifiers and paths exactly from bounded_context; never create or repair identifiers.",
            "Honor response_limits strictly; prefer fewer grounded items and shorter prose over truncating JSON.",
        ],
        "grounding_rules": {
            "static_facts_are_authoritative": True,
            "cite_only_supplied_fact_ids_and_paths": True,
            "do_not_invent_metrics": True,
            "do_not_include_raw_source_in_output": True,
        },
    }


def _stage_token_budget(config: dict[str, Any], stage: str) -> tuple[int, int, int, float]:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    actor = agents.get(STAGE_ACTORS[stage]) if isinstance(agents.get(STAGE_ACTORS[stage]), dict) else {}
    profile_name = str(actor.get("llm_config") or llm.get("default_config") or "analysis")
    profiles = llm.get("configs") if isinstance(llm.get("configs"), dict) else {}
    profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else {}
    analysis = config.get("llm_analysis") if isinstance(config.get("llm_analysis"), dict) else {}
    context_size = max(1, int(profile.get("context_size") or llm.get("context_size") or 32_768))
    completion_reserve = max(1, int(profile.get("max_tokens") or llm.get("max_tokens") or 4_096))
    safety_margin = max(0, int(analysis.get("token_safety_margin") or 2_048))
    bytes_per_token = min(8.0, max(1.0, float(analysis.get("estimated_bytes_per_token") or 3.0)))
    return context_size, completion_reserve, safety_margin, bytes_per_token


def _estimate_tokens(text: str, bytes_per_token: float) -> int:
    return max(1, math.ceil(len(text.encode("utf-8")) / bytes_per_token))


def _compact_source_packet_to_budget(
    context: dict[str, Any],
    *,
    input_budget: int,
    render: Callable[[dict[str, Any]], tuple[str, int]],
) -> dict[str, Any]:
    files = context.get("files") if isinstance(context.get("files"), list) else []
    excerpts = [str(item.get("excerpt") or "") if isinstance(item, dict) else "" for item in files]

    def with_excerpt_cap(cap: int) -> dict[str, Any]:
        candidate = copy.deepcopy(context)
        candidate_files = candidate.get("files") if isinstance(candidate.get("files"), list) else []
        for item, original in zip(candidate_files, excerpts):
            if not isinstance(item, dict):
                continue
            item["excerpt"] = original[:cap]
            item["excerpt_truncated"] = bool(item.get("excerpt_truncated")) or len(original) > cap
        limits = candidate.setdefault("packet_limits", {})
        limits["effective_max_chars_per_file"] = cap
        limits["token_budget_compacted"] = True
        return candidate

    best: dict[str, Any] | None = None
    low, high = 0, max((len(value) for value in excerpts), default=0)
    while low <= high:
        midpoint = (low + high) // 2
        candidate = with_excerpt_cap(midpoint)
        _prompt, estimated = render(candidate)
        if estimated <= input_budget:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    if best is not None:
        return best

    no_excerpts = with_excerpt_cap(0)
    facts = no_excerpts.get("facts") if isinstance(no_excerpts.get("facts"), list) else []
    if not facts:
        return no_excerpts

    minimum_facts = min(8, len(facts))
    low, high = minimum_facts, len(facts)
    while low <= high:
        midpoint = (low + high) // 2
        candidate = copy.deepcopy(no_excerpts)
        candidate["facts"] = facts[:midpoint]
        limits = candidate.setdefault("packet_limits", {})
        limits["facts_included"] = midpoint
        limits["facts_available"] = len(facts)
        limits["facts_truncated"] = midpoint < len(facts)
        _prompt, estimated = render(candidate)
        if estimated <= input_budget:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best or no_excerpts


def _compact_structured_packet_to_budget(
    context: dict[str, Any],
    *,
    input_budget: int,
    render: Callable[[dict[str, Any]], tuple[str, int]],
) -> dict[str, Any]:
    """Retain cited facts first, then fit as many additional facts as possible."""
    facts = context.get("facts") if isinstance(context.get("facts"), list) else []
    if not facts:
        return context
    known = {
        str(item.get("fact_id"))
        for item in facts
        if isinstance(item, dict) and item.get("fact_id")
    }
    referenced = _collect_exact_strings(
        {key: value for key, value in context.items() if key != "facts"},
        allowed=known,
    )
    optional_indexes = [
        index for index, item in enumerate(facts)
        if not isinstance(item, dict) or str(item.get("fact_id") or "") not in referenced
    ]

    def with_optional_count(count: int) -> dict[str, Any]:
        included_optional = set(optional_indexes[:count])
        candidate = copy.deepcopy(context)
        candidate["facts"] = [
            item for index, item in enumerate(facts)
            if index in included_optional
            or (isinstance(item, dict) and str(item.get("fact_id") or "") in referenced)
        ]
        limits = candidate.setdefault("packet_limits", {})
        limits.update({
            "token_budget_compacted": True,
            "facts_available": len(facts),
            "facts_included": len(candidate["facts"]),
            "facts_truncated": len(candidate["facts"]) < len(facts),
            "referenced_facts_preserved": len(referenced),
        })
        return candidate

    best: dict[str, Any] | None = None
    low, high = 0, len(optional_indexes)
    while low <= high:
        midpoint = (low + high) // 2
        candidate = with_optional_count(midpoint)
        _prompt, estimated = render(candidate)
        if estimated <= input_budget:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best or with_optional_count(0)


def _collect_exact_strings(value: Any, *, allowed: set[str]) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(
            _collect_exact_strings(item, allowed=allowed) for item in value.values()
        )) if value else set()
    if isinstance(value, list):
        return set().union(*(
            _collect_exact_strings(item, allowed=allowed) for item in value
        )) if value else set()
    candidate = str(value or "")
    return {candidate} if candidate in allowed else set()


def structured_packet(state: dict[str, Any], **values: Any) -> dict[str, Any]:
    facts = ((state.get("architecture_facts") or {}).get("facts") or [])[:240]
    return {
        "packet_kind": "validated_architecture_evidence",
        "repository_profile": _compact_repository_profile(state.get("repository_profile") or {}),
        "metrics": _compact_metrics(state.get("metrics") or {}),
        "evidence_availability": state.get("evidence_availability") or {},
        "facts": [_compact_fact(item) for item in facts if isinstance(item, dict)],
        "packet_limits": {
            "base_evidence_compacted": True,
            "facts_available": len((state.get("architecture_facts") or {}).get("facts") or []),
            "facts_included": len(facts),
        },
        **values,
    }


def _compact_repository_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    retained = (
        "schema_version", "languages", "packages", "applications", "entrypoints",
        "frameworks", "data_stores", "queues", "architecture_documents", "ci_files",
        "source_file_count", "symbol_count", "internal_dependency_count",
    )
    result = {key: profile.get(key) for key in retained if key in profile}
    metadata = profile.get("metadata_files") if isinstance(profile.get("metadata_files"), list) else []
    result["metadata_files"] = [
        {key: item.get(key) for key in ("path", "kind") if key in item}
        for item in metadata[:40]
        if isinstance(item, dict)
    ]
    observations = profile.get("documentation_observations") if isinstance(profile.get("documentation_observations"), list) else []
    marker_counts: dict[str, int] = {}
    observation_paths: list[str] = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        if path and path not in observation_paths:
            observation_paths.append(path)
        for marker in item.get("matched_markers") or []:
            name = str(marker)
            marker_counts[name] = marker_counts.get(name, 0) + 1
    result["documentation_observation_summary"] = {
        "count": len(observations),
        "paths": observation_paths[:20],
        "matched_marker_counts": marker_counts,
    }
    return result


def _compact_metrics(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    retained = (
        "schema_version", "module_count", "dependency_edge_count", "external_import_count",
        "cycle_count", "cycles", "cross_boundary_dependency_count",
        "cross_boundary_dependencies", "large_modules", "limitations", "symbol_count",
        "endpoint_count", "state_store_count", "trust_boundary_candidate_count",
        "test_file_count", "direct_test_gap_count", "deployment_descriptor_count",
        "history_available",
    )
    result = {key: metrics.get(key) for key in retained if key in metrics}
    result["top_fan_in"] = list(metrics.get("top_fan_in") or [])[:8]
    result["top_fan_out"] = list(metrics.get("top_fan_out") or [])[:8]
    result["structural_hotspot_count"] = len(metrics.get("structural_hotspots") or [])
    return result


def _compact_fact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("fact_id", "fact_type", "evidence_type", "paths", "value", "confidence")
        if key in item
    }


def known_fact_ids(state: dict[str, Any]) -> set[str]:
    return {
        str(item.get("fact_id"))
        for item in ((state.get("architecture_facts") or {}).get("facts") or [])
        if item.get("fact_id")
    }


def known_paths(state: dict[str, Any]) -> set[str]:
    return {str(item.get("path")) for item in ((state.get("inventory") or {}).get("files") or []) if item.get("path")}


def validate_references(values: Any, allowed: set[str], *, allow_empty: bool = True) -> list[str] | None:
    if not isinstance(values, list):
        return [] if allow_empty else None
    result = list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
    if any(item not in allowed for item in result) or (not allow_empty and not result):
        return None
    return result


def text(value: Any, *, maximum: int = 5000) -> str:
    return str(value or "").strip()[:maximum]


def string_list(value: Any, *, maximum_items: int = 20, maximum_chars: int = 1200) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [text(item, maximum=maximum_chars) for item in value[:maximum_items] if text(item, maximum=maximum_chars)]


def _analysis_state(state: dict[str, Any]) -> dict[str, Any]:
    return state.setdefault("llm_analysis", {
        "schema_version": "mn.blueprint.software_architecture_advisor.llm_analysis.v1",
        "required_stage_order": list(STAGES),
        "required_stage_count": len(STAGES),
        "stages": {},
        "raw_prompts_persisted": False,
        "raw_source_persisted": False,
    })


def _refresh_analysis(state: dict[str, Any]) -> None:
    analysis = _analysis_state(state)
    stages = analysis.get("stages") if isinstance(analysis.get("stages"), dict) else {}
    records = [stages[name] for name in STAGES if isinstance(stages.get(name), dict)]
    completed = [item for item in records if item.get("status") in {"completed", "completed_fake"}]
    failed = [item for item in records if item.get("status") == "failed"]
    providers = {str(item.get("provider") or "unknown") for item in completed}
    models = {str(item.get("model") or "unknown") for item in completed}
    aggregate = {
        "provider": next(iter(providers)) if len(providers) == 1 else "multiple" if providers else "unknown",
        "model": next(iter(models)) if len(models) == 1 else "multiple" if models else "unknown",
        "calls": sum(int(item.get("calls") or 0) for item in records),
        "successful_calls": len(completed),
        "fallback_calls": sum(int(item.get("fallback_calls") or 0) for item in records),
        "input_tokens": sum(int(item.get("input_tokens") or 0) for item in completed),
        "output_tokens": sum(int(item.get("output_tokens") or 0) for item in completed),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in completed),
        "estimated_tokens": sum(int(item.get("estimated_tokens") or 0) for item in completed),
        "provider_response_count": sum(int(item.get("provider_response_count") or 0) for item in completed),
        "validation_retries": sum(int(item.get("validation_retries") or 0) for item in completed),
        "failed_stages": [item["stage"] for item in failed],
    }
    analysis["aggregate_usage"] = aggregate
    analysis["completed_stage_count"] = len(completed)
    analysis["fallback_calls"] = aggregate["fallback_calls"]
    analysis["status"] = "failed" if failed else "completed" if len(completed) == len(STAGES) else "in_progress"
    state["llm_usage"] = aggregate


def _load_budget(ctx: dict[str, Any], config: dict[str, Any]) -> ActionBudget:
    raw_declared = (config.get("research_budget") or {}).get("default_actions")
    declared = len(STAGES) if raw_declared is None else int(raw_declared)
    budget = ActionBudget(min(len(STAGES), max(0, declared)))
    saved = WorkflowStateStore(Path(ctx["run_dir"])).read(_LEDGER_FILE, {})
    if isinstance(saved, dict):
        budget.used = int(saved.get("used") or 0)
        budget.actions = [dict(item) for item in saved.get("actions") or [] if isinstance(item, dict)]
    return budget


def _persist_budget(ctx: dict[str, Any], budget: ActionBudget) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(_LEDGER_FILE, budget.summary(include_actions=True))


def _append_observation(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": redact_observation_value(payload)}
    with (run_dir / _TRACE_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _append_resource(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": redact_observation_value(payload)}
    with (run_dir / "resources.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _append_stage_trace(ctx: dict[str, Any], record: dict[str, Any]) -> None:
    metadata = {key: value for key, value in record.items() if key != "output"}
    _append_observation(Path(ctx["run_dir"]), "architecture_llm_stage", metadata)


def _usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    return {
        key: max(0, int(after.get(key) or 0) - int(before.get(key) or 0))
        for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens")
    }


def _load_prompt(ctx: dict[str, Any], stage: str) -> str:
    candidates = [
        Path(__file__).resolve().parents[1] / "prompts" / _PROMPT_FILES[stage],
        Path(ctx.get("blueprint_dir") or "") / "payloads" / "prompts" / _PROMPT_FILES[stage],
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing prompt for required LLM stage {stage}.")


def _selected_paths(root: Path, state: dict[str, Any], *, stage: str, max_files: int) -> list[str]:
    available = known_paths(state)
    if not available:
        available = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and (path.suffix.lower() in _SAFE_SUFFIXES or path.name.lower() in _METADATA_NAMES)
        }
    docs = sorted(path for path in available if Path(path).name.lower() in _METADATA_NAMES or Path(path).suffix.lower() in {".md", ".toml", ".json", ".yaml", ".yml"})
    entrypoints = [str(item.get("path")) for item in ((state.get("repository_profile") or {}).get("entrypoints") or []) if item.get("path") in available]
    hotspots = [str(item.get("path")) for item in (state.get("hotspots") or []) if item.get("path") in available]
    graph_paths = [str(item.get("path")) for item in ((state.get("graph") or {}).get("nodes") or []) if item.get("path") in available]
    candidates = docs if stage == "source_intake" else [*docs[:6], *entrypoints, *hotspots, *graph_paths]
    result: list[str] = []
    for path in candidates:
        if path not in result and not _sensitive_path(path):
            result.append(path)
        if len(result) >= max_files:
            break
    return result


def _sensitive_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def _context_item_count(context: dict[str, Any]) -> int:
    return sum(len(value) for value in context.values() if isinstance(value, (list, dict)))


__all__ = [
    "STAGES", "build_source_packet", "fake_mode", "known_fact_ids", "known_paths",
    "run_model_stage", "string_list", "structured_packet", "text", "validate_references",
]
