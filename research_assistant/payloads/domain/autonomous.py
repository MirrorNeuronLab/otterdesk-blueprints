"""Isolated hypothesis generation, critique, tool use, and bounded code probes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mn_autonomous_research_skill import AutonomousResearchSession, GeneratedCodePolicy, ToolRegistry, create_research_goal
from mn_blueprint_support import llm_usage, resolve_actor_specs, run_actor_reviews

from .common import RESEARCH_ACTIONS, _json_safe, load_prompt, quick_test_enabled
from .evidence import (
    deterministic_research_posture,
    research_evidence,
    research_public_sources,
    sanitize_public_text,
)
from .state import _inputs, _save, _state
from .synthesis import evidence_digest, evidence_links_for_hypothesis, normalize_source_refs
from .runtime_services import init_research_llm


def _normalize_experiment(value: Any, hypothesis: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    measurements = raw.get("measurements") if isinstance(raw.get("measurements"), list) else []
    procedure = raw.get("procedure") if isinstance(raw.get("procedure"), list) else []
    stop_conditions = raw.get("stop_conditions") if isinstance(raw.get("stop_conditions"), list) else []
    return {
        "objective": str(raw.get("objective") or f"Test whether the proposed mechanism changes the predicted outcome: {hypothesis.get('statement')}")[:1000],
        "unit_of_analysis": str(raw.get("unit_of_analysis") or "One independently observed unit defined before data collection.")[:500],
        "baseline": str(raw.get("baseline") or "Matched status-quo condition recorded before applying the proposed change.")[:1000],
        "intervention": str(raw.get("intervention") or hypothesis.get("statement") or "")[:1000],
        "primary_outcome": str(raw.get("primary_outcome") or hypothesis.get("prediction") or "")[:1000],
        "measurements": [str(item)[:500] for item in measurements[:12]] or [
            "Primary outcome named in the prediction",
            "Exposure or intervention fidelity",
            "Known confounders and quality-boundary violations",
        ],
        "procedure": [str(item)[:1000] for item in procedure[:12]] or [
            "Define the experimental unit, inclusion rules, baseline, primary outcome, and analysis plan before collecting comparison data.",
            "Record a matched baseline under the same sampling, environment, and quality checks planned for the intervention.",
            "Apply the proposed change to a bounded comparison group while holding named confounders constant or measuring them.",
            "Repeat enough independent units to report dispersion and uncertainty, not only an average.",
            "Compare intervention and baseline outcomes, run the pre-specified sensitivity checks, and record all deviations.",
        ],
        "decision_rule": str(raw.get("decision_rule") or f"Escalate for review only if the prediction is observed and the disconfirming condition is not: {hypothesis.get('disconfirming_observation')}")[:1200],
        "analysis_plan": str(raw.get("analysis_plan") or "Report effect size, uncertainty, missingness, deviations, and sensitivity to measured confounders.")[:1200],
        "stop_conditions": [str(item)[:700] for item in stop_conditions[:10]] or [
            "A safety, ethics, privacy, or scope boundary is reached.",
            "Measurement integrity or intervention fidelity cannot be verified.",
        ],
    }


def _fallback_hypotheses(
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    documents: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    seed_hypotheses = list(inputs.get("seed_hypotheses") or [])
    goal = str(inputs.get("research_goal") or "").strip().rstrip(".")
    if not seed_hypotheses:
        seed_hypotheses = [
            f"A controlled intervention addressing this goal may change a pre-specified target outcome: {goal or 'unspecified research goal'}."
        ]
    hypotheses: list[dict[str, Any]] = []
    valid_refs = set(evidence.get("source_refs") or [])
    for seed in seed_hypotheses[:3]:
        raw = dict(seed) if isinstance(seed, dict) else {"statement": str(seed)}
        statement = str(raw.get("statement") or raw.get("hypothesis") or "").strip()[:800]
        hypothesis = {
            "statement": statement,
            "prediction": str(raw.get("prediction") or f"A matched comparison implementing this hypothesis produces a measurable, directionally consistent change relative to baseline: {statement}")[:1000],
            "counterargument": str(raw.get("counterargument") or "A competing mechanism, selection effect, implementation difference, or measurement artifact could produce the same apparent result.")[:1000],
            "disconfirming_observation": str(raw.get("disconfirming_observation") or "The predicted change is absent, reverses direction, or disappears after the named controls and sensitivity checks are applied.")[:1000],
            "assumptions": [str(item)[:500] for item in raw.get("assumptions", [])[:10]] if isinstance(raw.get("assumptions"), list) else [],
            "evidence_status": str(raw.get("evidence_status") or "candidate_context_not_validated")[:100],
        }
        if documents or sources:
            hypothesis["evidence_support"] = raw.get("evidence_support") or []
            refs, links = evidence_links_for_hypothesis(
                hypothesis, documents or [], sources or []
            )
        else:
            refs = normalize_source_refs(raw.get("evidence_support"), valid_refs)
            refs = refs or list(valid_refs)[:4]
            links = [
                {"source_ref": ref, "relationship": "candidate_context_not_validation"}
                for ref in refs
            ]
        hypothesis["evidence_support"] = refs
        hypothesis["evidence_links"] = links
        hypothesis["experiment"] = _normalize_experiment(raw.get("experiment"), hypothesis)
        hypotheses.append(hypothesis)
    return hypotheses


def _normalize_hypotheses(
    candidates: Any,
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    documents: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    raw = candidates if isinstance(candidates, list) else []
    normalized: list[dict[str, Any]] = []
    for candidate in raw[:3]:
        if not isinstance(candidate, dict):
            continue
        statement = str(candidate.get("statement") or candidate.get("hypothesis") or "").strip()
        if not statement:
            continue
        item = {
                "hypothesis_id": f"H{len(normalized) + 1}",
                "statement": statement[:800],
                "prediction": str(candidate.get("prediction") or f"A matched comparison produces a measurable change relative to baseline: {statement}")[:1000],
                "counterargument": str(candidate.get("counterargument") or "A competing mechanism, selection effect, implementation difference, or measurement artifact could account for the observation.")[:1000],
                "disconfirming_observation": str(candidate.get("disconfirming_observation") or "The predicted change is absent, reverses direction, or disappears after the named controls and sensitivity checks are applied.")[:1000],
                "assumptions": [str(value)[:500] for value in candidate.get("assumptions", [])[:10]] if isinstance(candidate.get("assumptions"), list) else [],
                "evidence_status": str(candidate.get("evidence_status") or "candidate_context_not_validated")[:100],
                "status": "hypothesis_for_review",
            }
        item["evidence_support"] = candidate.get("evidence_support") or []
        refs, links = evidence_links_for_hypothesis(item, documents or [], sources or [])
        if not (documents or sources):
            refs = normalize_source_refs(item["evidence_support"], set(evidence.get("source_refs") or []))
            links = [{"source_ref": ref, "relationship": "candidate_context_not_validation"} for ref in refs]
        item["evidence_support"] = refs
        item["evidence_links"] = links
        item["experiment"] = _normalize_experiment(candidate.get("experiment"), item)
        normalized.append(item)
    if not normalized:
        normalized = _fallback_hypotheses(inputs, evidence, documents, sources)
        for index, item in enumerate(normalized, start=1):
            item["hypothesis_id"] = f"H{index}"
            item["status"] = "hypothesis_for_review"
    return normalized


def _phase_generate_json(
    llm: Any,
    *,
    phase: str,
    instruction: str,
    context: dict[str, Any],
    fallback: dict[str, Any],
    phase_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run one explicit research phase and retain bounded call provenance."""
    phase_fallback = {"actor_id": f"research_phase:{phase}", **fallback}
    before_calls = int(getattr(llm, "calls", 0) or 0)
    before_fallbacks = int(getattr(llm, "fallback_calls", 0) or 0)
    response = llm.generate_json(
        system_prompt=(
            f"{load_prompt('research-packet-system.md')}\n\n"
            f"Research phase: {phase}.\n{instruction}\n"
            "Use only supplied evidence. Preserve exact source_ref values. "
            "Separate observed facts, inferences, hypotheses, and unknowns. "
            "Return only the requested compact JSON object. The entire response must "
            "fit under 800 tokens: use one short sentence per string, keep arrays to "
            "at most three items unless this phase explicitly requires more, never "
            "repeat source excerpts or inputs, and add no unrequested fields."
        ),
        user_prompt=json.dumps(context, sort_keys=True, default=str),
        fallback=phase_fallback,
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"Research LLM phase {phase!r} returned a non-object response.")
    phase_trace.append(
        {
            "phase": phase,
            "status": "completed",
            "llm_calls": max(0, int(getattr(llm, "calls", 0) or 0) - before_calls),
            "fallback_calls": max(
                0,
                int(getattr(llm, "fallback_calls", 0) or 0) - before_fallbacks,
            ),
            "source_refs": list(
                dict.fromkeys(
                    str(item)
                    for item in context.get("source_refs", [])
                    if str(item).strip()
                )
            )[:20],
        }
    )
    response.pop("actor_id", None)
    return response


def _fallback_source_analysis(
    digest: list[dict[str, Any]], evidence: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source_assessments": [
            {
                "source_ref": item.get("source_ref"),
                "source_type": item.get("kind"),
                "relevant_observations": [],
                "limitations": [
                    "Source content was indexed as context but not independently validated."
                ],
                "use_in_synthesis": "candidate_context_only",
            }
            for item in digest
        ],
        "cross_source_agreements": [],
        "cross_source_tensions": [],
        "evidence_gaps": list(evidence.get("evidence_gaps") or []),
    }


def _compact_hypothesis(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "hypothesis_id",
            "statement",
            "prediction",
            "counterargument",
            "disconfirming_observation",
            "assumptions",
            "evidence_support",
            "evidence_status",
        )
    }


def _compact_research_request(inputs: dict[str, Any]) -> dict[str, Any]:
    """Exclude bulky seed test plans and local paths from model phase prompts."""
    return {
        "research_goal": str(inputs.get("research_goal") or "")[:600],
        "research_domain": str(inputs.get("research_domain") or "")[:120],
        "research_question": str(inputs.get("research_question") or "")[:600],
        "scope": str(inputs.get("scope") or "")[:600],
        "success_criteria": _text_items(
            inputs.get("success_criteria"), limit=6, chars=200
        ),
        "constraints": {
            str(key)[:100]: _json_safe(value)
            for key, value in list((inputs.get("constraints") or {}).items())[:12]
        }
        if isinstance(inputs.get("constraints"), dict)
        else {},
    }


def _compact_seed_hypotheses(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    seeds = inputs.get("seed_hypotheses")
    raw_seeds = seeds if isinstance(seeds, list) else []
    compact: list[dict[str, Any]] = []
    for seed in raw_seeds[:3]:
        item = seed if isinstance(seed, dict) else {"statement": str(seed)}
        compact.append(
            {
                "statement": str(
                    item.get("statement") or item.get("hypothesis") or ""
                )[:500],
                "prediction": str(item.get("prediction") or "")[:500],
                "counterargument": str(item.get("counterargument") or "")[:400],
                "disconfirming_observation": str(
                    item.get("disconfirming_observation") or ""
                )[:400],
                "evidence_support": _text_items(
                    item.get("evidence_support"), limit=4, chars=120
                ),
            }
        )
    return compact


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text_items(value: Any, *, limit: int = 20, chars: int = 1000) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:chars] for item in value[:limit] if str(item).strip()]


def _safe_rank(value: Any, default: int) -> int:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return default
    return rank if rank > 0 else default


def _normalize_source_analysis(
    value: dict[str, Any],
    fallback: dict[str, Any],
    valid_refs: set[str],
) -> dict[str, Any]:
    assessments = []
    for item in _dict_items(value.get("source_assessments")):
        source_ref = str(item.get("source_ref") or "").strip()
        if source_ref not in valid_refs:
            continue
        assessments.append(
            {
                "source_ref": source_ref,
                "source_type": str(item.get("source_type") or "unknown")[:100],
                "relevant_observations": _text_items(
                    item.get("relevant_observations"), limit=12
                ),
                "limitations": _text_items(item.get("limitations"), limit=10),
                "use_in_synthesis": str(
                    item.get("use_in_synthesis") or "candidate_context_only"
                )[:500],
            }
        )
    if not assessments:
        assessments = _dict_items(fallback.get("source_assessments"))
    return {
        "source_assessments": assessments,
        "cross_source_agreements": _text_items(
            value.get("cross_source_agreements"), limit=20
        ),
        "cross_source_tensions": _text_items(
            value.get("cross_source_tensions"), limit=20
        ),
        "evidence_gaps": _text_items(value.get("evidence_gaps"), limit=20)
        or _text_items(fallback.get("evidence_gaps"), limit=20),
    }


def _normalize_question_decomposition(
    value: dict[str, Any], fallback: dict[str, Any]
) -> dict[str, Any]:
    subquestions = _dict_items(value.get("subquestions")) or _dict_items(
        fallback.get("subquestions")
    )
    return {
        "subquestions": [
            {
                "subquestion_id": str(
                    item.get("subquestion_id") or f"Q{index}"
                )[:40],
                "question": str(item.get("question") or "")[:1000],
                "decision_relevance": str(
                    item.get("decision_relevance") or ""
                )[:1000],
                "evidence_needed": _text_items(
                    item.get("evidence_needed"), limit=12, chars=500
                ),
            }
            for index, item in enumerate(subquestions[:12], start=1)
            if str(item.get("question") or "").strip()
        ],
        "key_definitions": _dict_items(value.get("key_definitions"))
        or _text_items(value.get("key_definitions"), limit=20),
        "assumptions_to_test": _text_items(
            value.get("assumptions_to_test"), limit=20
        ),
        "stop_conditions": _text_items(value.get("stop_conditions"), limit=20)
        or _text_items(fallback.get("stop_conditions"), limit=20),
    }


def _prepare_deep_research(
    llm: Any,
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    rag: dict[str, Any],
    posture: dict[str, Any],
    documents: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Read evidence, decompose the question, generate rivals, and plan probes."""
    phase_trace: list[dict[str, Any]] = []
    digest = evidence_digest(documents, sources, max_chars=8000, per_source_chars=1600)
    source_refs = list(evidence.get("source_refs") or [])
    source_analysis_fallback = _fallback_source_analysis(digest, evidence)
    source_analysis = _phase_generate_json(
        llm,
        phase="source_analysis",
        instruction=(
            "Read every source excerpt. Extract only observations actually stated, assess limitations, "
            "and identify agreements, tensions, and missing evidence. Return source_assessments, "
            "cross_source_agreements, cross_source_tensions, and evidence_gaps. Include one assessment "
            "per supplied source_ref, with at most two short observations and two short limitations."
        ),
        context={
            "research_question": inputs.get("research_question"),
            "scope": inputs.get("scope"),
            "source_refs": source_refs,
            "source_digest": digest,
            "deterministic_evidence": evidence,
        },
        fallback=source_analysis_fallback,
        phase_trace=phase_trace,
    )
    source_analysis = _normalize_source_analysis(
        source_analysis, source_analysis_fallback, set(source_refs)
    )
    question_decomposition_fallback = {
        "subquestions": [
            {
                "subquestion_id": "Q1",
                "question": inputs.get("research_question")
                or inputs.get("research_goal"),
                "decision_relevance": "Directly addresses the supplied research decision.",
                "evidence_needed": source_refs[:4],
            }
        ],
        "key_definitions": [],
        "assumptions_to_test": [],
        "stop_conditions": [
            "Stop if the supplied evidence cannot support a traceable comparison."
        ],
    }
    question_decomposition = _phase_generate_json(
        llm,
        phase="question_decomposition",
        instruction=(
            "Decompose the decision into distinct answerable subquestions. Define ambiguous terms, "
            "name assumptions that must be tested, and state what evidence would answer each subquestion. "
            "Return at most four subquestions, three key_definitions, three assumptions_to_test, and "
            "three stop_conditions."
        ),
        context={
            "research_goal": inputs.get("research_goal"),
            "research_question": inputs.get("research_question"),
            "scope": inputs.get("scope"),
            "success_criteria": inputs.get("success_criteria"),
            "constraints": inputs.get("constraints"),
            "source_refs": source_refs,
            "source_analysis": source_analysis,
        },
        fallback=question_decomposition_fallback,
        phase_trace=phase_trace,
    )
    question_decomposition = _normalize_question_decomposition(
        question_decomposition, question_decomposition_fallback
    )
    seed_candidates = _fallback_hypotheses(inputs, evidence, documents, sources)
    generation = _phase_generate_json(
        llm,
        phase="competing_hypothesis_generation",
        instruction=(
            "Generate at most three genuinely competing, falsifiable mechanism hypotheses—not cosmetic "
            "variations. For each return statement, prediction, evidence_support, counterargument, "
            "disconfirming_observation, assumptions, and evidence_status. Keep every field to one short "
            "sentence, use at most two assumptions, and do not return experiment objects; a later phase "
            "designs the tests."
        ),
        context={
            "research_request": _compact_research_request(inputs),
            "source_refs": source_refs,
            "source_analysis": source_analysis,
            "question_decomposition": question_decomposition,
            "retrieved_method_context": str(rag.get("context") or "")[:2500],
            "seed_hypotheses_to_challenge": _compact_seed_hypotheses(inputs),
        },
        fallback={
            **posture,
            "candidate_hypotheses": seed_candidates,
        },
        phase_trace=phase_trace,
    )
    candidates = _normalize_hypotheses(
        generation.get("candidate_hypotheses"), inputs, evidence, documents, sources
    )
    critiques: list[dict[str, Any]] = []
    for hypothesis in candidates:
        critique_response = _phase_generate_json(
            llm,
            phase=f"adversarial_review_{hypothesis['hypothesis_id']}",
            instruction=(
                "Act as a hostile but fair methodological reviewer. Find the strongest alternative "
                "explanations, confounders, measurement failures, boundary conditions, and decisive "
                "disconfirming observations. Recommend a concrete revision without inventing evidence. "
                "Use at most two items in each array and one short sentence per item."
            ),
            context={
                "research_question": inputs.get("research_question"),
                "source_refs": source_refs,
                "hypothesis": _compact_hypothesis(hypothesis),
                "source_analysis": source_analysis,
                "question_decomposition": question_decomposition,
            },
            fallback={
                "hypothesis_id": hypothesis["hypothesis_id"],
                "strongest_counterargument": hypothesis.get("counterargument"),
                "alternative_explanations": [],
                "confounders": [],
                "measurement_risks": [],
                "boundary_conditions": [],
                "decisive_disconfirming_observations": [
                    hypothesis.get("disconfirming_observation")
                ],
                "revision_recommendation": "Retain as a review-only hypothesis pending the named test.",
            },
            phase_trace=phase_trace,
        )
        critique_response["hypothesis_id"] = hypothesis["hypothesis_id"]
        critiques.append(critique_response)

    tool_plan = _phase_generate_json(
        llm,
        phase="gap_and_probe_planning",
        instruction=(
            "Choose only allowlisted probes that can resolve a named evidence or reasoning gap. "
            "Return tool_requests and optional generated_python. Generated Python may only perform "
            "bounded descriptive, ranking, sensitivity, or consistency analysis on supplied data. "
            "Return at most two tool requests and no prose outside those fields."
        ),
        context={
            "research_question": inputs.get("research_question"),
            "source_refs": source_refs,
            "source_analysis": source_analysis,
            "question_decomposition": question_decomposition,
            "candidate_hypotheses": [_compact_hypothesis(item) for item in candidates],
            "critique_ledger": critiques,
            "available_tools": [
                "document_extract",
                "knowledge_retrieve",
                "hypothesis_rank",
                "browser_search",
                "browser_page",
            ],
        },
        fallback={"tool_requests": [], "generated_python": ""},
        phase_trace=phase_trace,
    )
    recommendation = {
        "recommended_action": str(
            generation.get("recommended_action") or posture["recommended_action"]
        ),
        "confidence": str(generation.get("confidence") or posture["confidence"]),
        "rationale": str(generation.get("rationale") or posture["rationale"])[:2000],
        "candidate_hypotheses": candidates,
        "tool_requests": tool_plan.get("tool_requests")
        if isinstance(tool_plan.get("tool_requests"), list)
        else [],
        "generated_python": str(tool_plan.get("generated_python") or "")[:40000],
    }
    deep_state = {
        "source_analysis": source_analysis,
        "question_decomposition": question_decomposition,
        "critique_ledger": critiques,
        "phase_trace": phase_trace,
        "source_refs": source_refs,
        "source_digest": digest,
    }
    return recommendation, deep_state, phase_trace


def _finalize_deep_research(
    llm: Any,
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    documents: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    posture: dict[str, Any],
    recommendation: dict[str, Any],
    deep_state: dict[str, Any],
    observations: list[dict[str, Any]],
    code_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Revise against observations, design tests, then perform meta-review."""
    phase_trace = deep_state["phase_trace"]
    revision = _phase_generate_json(
        llm,
        phase="evidence_and_probe_revision",
        instruction=(
            "Revise, merge, or reject candidate hypotheses in light of the source analysis, adversarial "
            "reviews, and probe observations. Do not treat tool or code output as empirical validation. "
            "Return the complete revised candidate_hypotheses plus rationale, recommended_action, and "
            "confidence. Keep every hypothesis field to one short sentence, use at most two assumptions, "
            "and do not return experiment objects."
        ),
        context={
            "research_request": _compact_research_request(inputs),
            "source_refs": deep_state["source_refs"],
            "source_analysis": deep_state["source_analysis"],
            "question_decomposition": deep_state["question_decomposition"],
            "candidate_hypotheses": [
                _compact_hypothesis(item)
                for item in recommendation.get("candidate_hypotheses") or []
            ],
            "critique_ledger": deep_state["critique_ledger"],
            "tool_observations": observations,
            "generated_code_result": code_result,
        },
        fallback={
            "candidate_hypotheses": recommendation.get("candidate_hypotheses") or [],
            "rationale": recommendation.get("rationale"),
            "recommended_action": recommendation.get("recommended_action"),
            "confidence": recommendation.get("confidence"),
        },
        phase_trace=phase_trace,
    )
    candidates = _normalize_hypotheses(
        revision.get("candidate_hypotheses"), inputs, evidence, documents, sources
    )
    experiment_traces: list[dict[str, Any]] = []
    experiments_by_id: dict[str, dict[str, Any]] = {}
    for item in candidates:
        hypothesis_id = item["hypothesis_id"]
        critique = next(
            (
                value
                for value in deep_state["critique_ledger"]
                if value.get("hypothesis_id") == hypothesis_id
            ),
            {},
        )
        fallback_experiment = {
            "hypothesis_id": hypothesis_id,
            **_normalize_experiment(item.get("experiment"), item),
        }
        design = _phase_generate_json(
            llm,
            phase=f"experiment_design_{hypothesis_id}",
            instruction=(
                "Design one decision-useful, review-only test for this hypothesis. Return one experiment "
                "object with hypothesis_id, objective, unit_of_analysis, baseline, intervention, "
                "primary_outcome, measurements, procedure, decision_rule, analysis_plan, and "
                "stop_conditions. Use at most five measurements, five short procedure steps, and three "
                "stop conditions so the complete object fits under 800 tokens."
            ),
            context={
                "research_question": inputs.get("research_question"),
                "constraints": inputs.get("constraints"),
                "source_refs": deep_state["source_refs"],
                "hypothesis": _compact_hypothesis(item),
                "adversarial_review": critique,
            },
            fallback={"experiment": fallback_experiment},
            phase_trace=experiment_traces,
        )
        experiment = design.get("experiment")
        if not isinstance(experiment, dict):
            legacy = _dict_items(design.get("experiments"))
            experiment = legacy[0] if legacy else fallback_experiment
        experiment["hypothesis_id"] = hypothesis_id
        experiments_by_id[hypothesis_id] = experiment
    phase_trace.append(
        {
            "phase": "experiment_design",
            "status": "completed",
            "llm_calls": sum(int(item.get("llm_calls") or 0) for item in experiment_traces),
            "fallback_calls": sum(
                int(item.get("fallback_calls") or 0) for item in experiment_traces
            ),
            "source_refs": list(deep_state["source_refs"])[:20],
            "hypothesis_ids": [item["hypothesis_id"] for item in candidates],
        }
    )
    for item in candidates:
        designed = experiments_by_id.get(item["hypothesis_id"])
        item["experiment"] = _normalize_experiment(designed, item)

    meta_review = _phase_generate_json(
        llm,
        phase="meta_review_and_ranking",
        instruction=(
            "Independently rank the hypotheses by traceable support, falsifiability, decision value, and "
            "risk of misleading the reviewer. Penalize unsupported causal or novelty claims. Return ranking, "
            "recommended_action, confidence, rationale, and unresolved_gaps. Use one short rationale per "
            "hypothesis and at most five unresolved gaps."
        ),
        context={
            "research_question": inputs.get("research_question"),
            "source_refs": deep_state["source_refs"],
            "source_analysis": deep_state["source_analysis"],
            "candidate_hypotheses": candidates,
            "critique_ledger": deep_state["critique_ledger"],
            "tool_observations": observations,
        },
        fallback={
            "ranking": [
                {
                    "hypothesis_id": item["hypothesis_id"],
                    "rank": index,
                    "priority_score": max(0, 100 - (index - 1) * 10),
                    "rationale": "Deterministic order pending qualified review.",
                }
                for index, item in enumerate(candidates, start=1)
            ],
            "recommended_action": revision.get("recommended_action")
            or posture["recommended_action"],
            "confidence": revision.get("confidence") or posture["confidence"],
            "rationale": revision.get("rationale") or posture["rationale"],
            "unresolved_gaps": list(evidence.get("evidence_gaps") or []),
        },
        phase_trace=phase_trace,
    )
    ranking_items = _dict_items(meta_review.get("ranking"))
    ranking_by_id = {
        str(item.get("hypothesis_id")): item
        for item in ranking_items
        if item.get("hypothesis_id")
    }
    for index, item in enumerate(candidates, start=1):
        rank = ranking_by_id.get(item["hypothesis_id"]) or {}
        item["rank"] = _safe_rank(rank.get("rank"), index)
        item["priority_score"] = rank.get("priority_score")
        item["ranking_rationale"] = str(
            rank.get("rationale") or "Pending qualified review."
        )[:1000]
    candidates.sort(key=lambda item: (item.get("rank") or 999, item["hypothesis_id"]))
    action = str(
        meta_review.get("recommended_action")
        or revision.get("recommended_action")
        or posture["recommended_action"]
    ).lower()
    if action not in RESEARCH_ACTIONS:
        action = posture["recommended_action"]
    confidence = str(
        meta_review.get("confidence")
        or revision.get("confidence")
        or posture["confidence"]
    ).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = posture["confidence"]
    executive_synthesis = _phase_generate_json(
        llm,
        phase="executive_synthesis",
        instruction=(
            "Write the decision-useful synthesis after ranking. Return executive_summary, key_findings, "
            "decision_implications, and caveats. Integrate the source analysis, hypothesis tests, critiques, "
            "and unresolved gaps; introduce no new facts and do not imply validation or authorization. "
            "Use at most three short items in each array and keep the summary under 120 words."
        ),
        context={
            "research_goal": inputs.get("research_goal"),
            "research_question": inputs.get("research_question"),
            "recommended_action": action,
            "confidence": confidence,
            "source_refs": deep_state["source_refs"],
            "source_analysis": deep_state["source_analysis"],
            "question_decomposition": deep_state["question_decomposition"],
            "ranked_hypotheses": candidates,
            "critique_ledger": deep_state["critique_ledger"],
            "unresolved_gaps": _text_items(
                meta_review.get("unresolved_gaps"), limit=20
            ),
        },
        fallback={
            "executive_summary": str(
                meta_review.get("rationale")
                or revision.get("rationale")
                or posture["rationale"]
            )[:2000],
            "key_findings": [],
            "decision_implications": [],
            "caveats": _text_items(
                meta_review.get("unresolved_gaps"), limit=20
            ),
        },
        phase_trace=phase_trace,
    )
    executive_synthesis = {
        "executive_summary": str(
            executive_synthesis.get("executive_summary")
            or meta_review.get("rationale")
            or revision.get("rationale")
            or posture["rationale"]
        )[:3000],
        "key_findings": _text_items(
            executive_synthesis.get("key_findings"), limit=12
        ),
        "decision_implications": _text_items(
            executive_synthesis.get("decision_implications"), limit=12
        ),
        "caveats": _text_items(executive_synthesis.get("caveats"), limit=12),
    }
    normalized_ranking = [
        {
            "hypothesis_id": item["hypothesis_id"],
            "rank": item["rank"],
            "priority_score": item.get("priority_score"),
            "rationale": item.get("ranking_rationale"),
        }
        for item in candidates
    ]
    return {
        "recommended_action": action,
        "confidence": confidence,
        "rationale": str(
            meta_review.get("rationale")
            or revision.get("rationale")
            or posture["rationale"]
        )[:2000],
        "candidate_hypotheses": candidates,
        "source_analysis": deep_state["source_analysis"],
        "question_decomposition": deep_state["question_decomposition"],
        "critique_ledger": deep_state["critique_ledger"],
        "ranking": normalized_ranking,
        "executive_synthesis": executive_synthesis,
        "unresolved_gaps": _text_items(
            meta_review.get("unresolved_gaps"), limit=20
        ),
        "tool_requests": [],
        "generated_python": "",
    }


def _document_tool(documents: list[dict[str, Any]], arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or arguments.get("source_ref") or "").strip().lower()
    matches = []
    for document in documents:
        haystack = f"{document.get('source_ref', '')} {document.get('name', '')} {document.get('text', '')}".lower()
        if not query or query in haystack:
            matches.append(
                {
                    "source_ref": document.get("source_ref"),
                    "name": document.get("name"),
                    "text": str(document.get("text") or "")[:4000],
                    "status": document.get("status"),
                }
            )
    return {"query": query, "matches": matches[:5]}


def _rank_hypotheses_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    candidates = arguments.get("candidates") if isinstance(arguments.get("candidates"), list) else []
    ranked = []
    for index, candidate in enumerate(candidates[:20]):
        item = candidate if isinstance(candidate, dict) else {"statement": str(candidate)}
        support = item.get("evidence_support") if isinstance(item.get("evidence_support"), list) else []
        ranked.append(
            {
                "index": index,
                "statement": str(item.get("statement") or item.get("hypothesis") or "")[:800],
                "traceable_support_count": len([ref for ref in support if str(ref).strip()]),
            }
        )
    ranked.sort(key=lambda item: (-item["traceable_support_count"], item["index"]))
    return {"ranking_rule": "traceable_support_count_then_input_order", "ranked": ranked}


def _actor_review_context(
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    recommendation: dict[str, Any],
    rag: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "research_request": {
            key: inputs.get(key)
            for key in ("research_goal", "research_domain", "research_question", "scope", "success_criteria", "constraints")
        },
        "evidence_posture": {
            key: evidence.get(key)
            for key in ("deterministic_checks", "evidence_gaps", "source_refs", "usable_local_document_count", "usable_public_source_count")
        },
        "candidate_hypotheses": [
            {
                "hypothesis_id": item.get("hypothesis_id"),
                "statement": str(item.get("statement") or "")[:500],
                "prediction": str(item.get("prediction") or "")[:500],
                "evidence_support": list(item.get("evidence_support") or [])[:6],
                "counterargument": str(item.get("counterargument") or "")[:500],
                "disconfirming_observation": str(
                    item.get("disconfirming_observation") or ""
                )[:500],
                "assumptions": [
                    str(value)[:250] for value in (item.get("assumptions") or [])[:5]
                ],
                "evidence_status": item.get("evidence_status"),
            }
            for item in recommendation.get("candidate_hypotheses") or []
        ],
        "rag": {
            "status": rag.get("status"),
            "citations": list(rag.get("citations") or [])[:12],
            "context": str(rag.get("context") or "")[:1000],
        },
        "public_sources": [
            {
                key: item.get(key)
                for key in ("source_ref", "title", "url", "status", "warning")
            }
            for item in sources[:12]
        ],
    }


def run_autonomous_research(
    llm: Any,
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    rag: dict[str, Any],
    posture: dict[str, Any],
    config: dict[str, Any],
    documents: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    workspace: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Run every autonomous subphase through one auditable session.

    The workflow manifest places this function in its isolated Docker worker.
    Direct fake-mode calls exercise the same contract for local tests.
    """

    autonomous_config = config.get("agentic_research") if isinstance(config.get("agentic_research"), dict) else {}
    allowed_tools = {
        str(item)
        for item in autonomous_config.get("allowed_tools") or []
        if str(item) in {"document_extract", "browser_search", "browser_page", "knowledge_retrieve", "hypothesis_rank", "finish"}
    }
    registry = ToolRegistry(allowed_tools)
    warnings: list[dict[str, Any]] = []
    if "document_extract" in allowed_tools:
        registry.register("document_extract", lambda arguments: _document_tool(documents, arguments))
    if "knowledge_retrieve" in allowed_tools:
        registry.register(
            "knowledge_retrieve",
            lambda arguments: {
                "query": str(arguments.get("query") or inputs.get("research_question") or inputs.get("research_goal"))[:1000],
                "context": str(rag.get("context") or "")[:6000],
                "citations": list(rag.get("citations") or [])[:20],
            },
        )
    if "hypothesis_rank" in allowed_tools:
        registry.register("hypothesis_rank", _rank_hypotheses_tool)
    if "finish" in allowed_tools:
        registry.register("finish", lambda arguments: {"status": "finished", "summary": str(arguments.get("summary") or "")[:2000]})

    quick_test = str((config.get("llm") or {}).get("mode") or "").lower() in {"fake", "mock"} or bool(
        (config.get("execution") or {}).get("quick_test")
    )

    def public_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = sanitize_public_text(arguments.get("query") or arguments.get("url") or "")
        if not query:
            raise ValueError("public research tool requires a privacy-safe query")
        observed, tool_warnings = research_public_sources([query], config, quick_test=quick_test)
        sources.extend(observed)
        warnings.extend(tool_warnings)
        return {"query": query, "sources": observed, "warnings": tool_warnings}

    for tool_name in ("browser_search", "browser_page"):
        if tool_name in allowed_tools:
            registry.register(tool_name, public_search)

    generated = autonomous_config.get("generated_code") if isinstance(autonomous_config.get("generated_code"), dict) else {}
    goal = create_research_goal(
        inputs.get("research_goal") or "Investigate the supplied research question",
        question=inputs.get("research_question") or "",
        success_criteria=list(inputs.get("success_criteria") or []),
        constraints=inputs.get("constraints") or {},
    )
    session = AutonomousResearchSession(
        goal,
        registry,
        workspace / str(generated.get("workspace") or "generated_research"),
        max_tool_calls=max(0, int(autonomous_config.get("max_total_tool_calls", 12))),
        code_policy=GeneratedCodePolicy(
            timeout_seconds=max(1, int(generated.get("timeout_seconds", 15))),
            max_output_chars=max(1000, int(generated.get("max_output_chars", 20000))),
            max_memory_mb=max(64, int(generated.get("max_memory_mb", 256))),
        ),
    )
    context_refs = list(dict.fromkeys([*(evidence.get("source_refs") or []), *(rag.get("citations") or [])]))[:30]
    session.create_prompt(
        phase="goal_expansion",
        instructions=["Refine the goal into falsifiable questions without widening the supplied constraints.", "Keep facts, assumptions, and unknowns separate."],
        context_refs=context_refs,
        allowed_tools=[],
    )
    session.create_prompt(
        phase="exploration_and_adversarial_generation",
        instructions=["Explore competing mechanisms, not variations of one idea.", "Request allowlisted skills only when they can resolve a named gap.", "Attach source references or label the result as a hypothesis."],
        context_refs=context_refs,
        allowed_tools=sorted(allowed_tools - {"finish"}),
    )
    session.create_prompt(
        phase="computational_probe_and_synthesis",
        instructions=["Use generated Python only for bounded ranking, sensitivity, or consistency analysis.", "Treat code output as an internal probe, never as empirical validation.", "Produce at most three falsifiable candidates for deterministic verification."],
        context_refs=context_refs,
        allowed_tools=["hypothesis_rank"] if "hypothesis_rank" in allowed_tools else [],
    )

    recommendation, deep_state, phase_trace = _prepare_deep_research(
        llm, inputs, evidence, rag, posture, documents, sources
    )
    observations: list[dict[str, Any]] = []
    for index, request in enumerate(recommendation.pop("tool_requests", [])[: session.max_tool_calls], start=1):
        if not isinstance(request, dict):
            continue
        tool = str(request.get("tool") or "")
        arguments = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
        try:
            observation = session.use_tool(tool, arguments)
            observations.append({"request_index": index, "tool": tool, "status": "completed", "observation": _json_safe(observation)})
        except Exception as exc:
            observations.append({"request_index": index, "tool": tool, "status": "failed", "error": str(exc)[:1000]})
            warnings.append({"status": "autonomous_tool_failed", "tool": tool, "message": str(exc)[:1000]})

    generated_python = recommendation.pop("generated_python", "")
    code_result: dict[str, Any] | None = None
    if generated_python and autonomous_config.get("allow_generated_code", True):
        try:
            code_result = session.execute_python(
                generated_python,
                input_payload={
                    "evidence": evidence,
                    "candidate_hypotheses": recommendation.get("candidate_hypotheses") or [],
                    "tool_observations": observations,
                },
            )
            if code_result.get("status") != "completed":
                warnings.append({"status": "generated_code_failed", "message": str(code_result.get("stderr") or code_result.get("status"))[:1000]})
        except Exception as exc:
            warnings.append({"status": "generated_code_rejected", "message": str(exc)[:1000]})

    recommendation = _finalize_deep_research(
        llm,
        inputs,
        research_evidence(inputs, documents, sources),
        documents,
        sources,
        posture,
        recommendation,
        deep_state,
        observations,
        code_result,
    )

    autonomous = {
        "schema_version": "mn.blueprint.autonomous_research.v1",
        "isolation_required": True,
        "runner": "docker_worker",
        "single_job_instance": True,
        "live_model_required": bool(
            ((config.get("llm") or {}).get("require_live", False))
            and not quick_test
        ),
        "session": session.snapshot(),
        "tool_observations": observations,
        "generated_code_result": code_result,
        "research_phase_trace": phase_trace,
        "source_analysis": recommendation.get("source_analysis") or {},
        "question_decomposition": recommendation.get("question_decomposition") or {},
        "critique_ledger": recommendation.get("critique_ledger") or [],
        "ranking": recommendation.get("ranking") or [],
        "executive_synthesis": recommendation.get("executive_synthesis") or {},
        "unresolved_gaps": recommendation.get("unresolved_gaps") or [],
        "synthesis_passes": len(phase_trace),
    }
    return recommendation, autonomous, warnings


def _experiment_concepts(hypotheses: list[dict[str, Any]], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = []
    for hypothesis in hypotheses:
        experiment = _normalize_experiment(hypothesis.get("experiment"), hypothesis)
        concepts.append(
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "design_status": "concept_for_human_review",
                **experiment,
                "approval_dependencies": ["qualified human review", *(["scope constraint review"] if inputs.get("constraints") else [])],
                "not_executed": True,
            }
        )
    return concepts


def autonomous_research(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm, action_budget = init_research_llm(ctx, llm_client)
    documents = state.get("documents") or []
    sources = state.get("sources") or []
    evidence = state.get("evidence") or research_evidence(inputs, documents, sources)
    posture = state.get("posture") or deterministic_research_posture(evidence)
    recommendation, autonomous, autonomous_warnings = run_autonomous_research(
        llm, inputs, evidence, state.get("rag") or {}, posture, ctx["config"], documents, sources,
        workspace=Path(os.environ.get("MN_WORKDIR") or Path(ctx["run_dir"]) / "workspace"),
    )
    verified_evidence = research_evidence(inputs, documents, sources)
    actor_findings = run_actor_reviews(
        config=ctx["config"], llm=llm, actor_ids=list(resolve_actor_specs(ctx["config"]).keys()), state={},
        task=load_prompt("research-review-task.md"),
        context=_actor_review_context(
            inputs,
            verified_evidence,
            recommendation,
            state.get("rag") or {},
            sources,
        ),
    )
    usage = llm_usage(llm)
    llm_config = ctx["config"].get("llm") if isinstance(ctx["config"].get("llm"), dict) else {}
    if (
        bool(llm_config.get("require_live", False))
        and not quick_test_enabled(ctx["config"])
        and int(usage.get("fallback_calls") or 0) > 0
    ):
        raise RuntimeError(
            "Research Assistant requires live model-backed synthesis; one or more research phases used fallback output."
        )
    state.update({"inputs": inputs, "evidence": verified_evidence, "posture": deterministic_research_posture(verified_evidence), "recommendation": recommendation, "autonomous": autonomous, "actor_findings": actor_findings, "warnings": [*(state.get("warnings") or []), *autonomous_warnings], "llm_usage": usage, "llm_action_budget": action_budget.summary(include_actions=True)})
    _save(ctx, state)
    return {"tool_calls": (autonomous.get("session") or {}).get("tool_calls_used", 0)}


__all__ = [
    "_document_tool",
    "_actor_review_context",
    "_experiment_concepts",
    "_fallback_hypotheses",
    "_normalize_hypotheses",
    "_rank_hypotheses_tool",
    "autonomous_research",
    "run_autonomous_research",
]
