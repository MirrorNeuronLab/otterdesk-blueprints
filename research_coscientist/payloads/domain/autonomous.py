"""Isolated hypothesis generation, critique, tool use, and bounded code probes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mn_autonomous_research_skill import AutonomousResearchSession, GeneratedCodePolicy, ToolRegistry, create_research_goal
from mn_blueprint_support import llm_usage, resolve_actor_specs, run_actor_reviews

from .common import RESEARCH_ACTIONS, _compact, _json_safe, load_prompt, research_llm
from .evidence import (
    deterministic_research_posture,
    research_evidence,
    research_public_sources,
    sanitize_public_text,
)
from .state import _inputs, _save, _state


def _fallback_hypotheses(inputs: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, Any]]:
    seed_hypotheses = list(inputs.get("seed_hypotheses") or [])
    refs = list(evidence.get("source_refs") or [])
    goal = str(inputs.get("research_goal") or "").strip().rstrip(".")
    question = str(inputs.get("research_question") or "").strip().rstrip(".")
    cooling_context = f"{goal} {question}".lower()
    if not seed_hypotheses and "cooling" in cooling_context and "energy" in cooling_context:
        return [
            {
                "statement": "During matched low-load conditions, a preapproved five-percentage-point pump-speed reduction may lower combined pump and fan power while preserving the required thermal margin.",
                "prediction": "At matched ambient temperature and thermal load, combined pump-plus-fan kW falls by at least 3% without breaching the operator-approved return-temperature or flow limit.",
                "evidence_support": refs[:4],
                "counterargument": "Lower flow could create unobserved local hot spots, and an apparent saving could instead reflect a cooler ambient condition or lighter IT load.",
                "disconfirming_observation": "Matched intervention runs show less than a 3% power reduction, unstable supply/return temperatures, or any thermal-limit breach.",
            },
            {
                "statement": "A wider, operator-approved fan-control deadband may reduce avoidable fan cycling and energy use during steady thermal load.",
                "prediction": "Compared with the current control schedule at matched ambient and load, fan kWh and start count decline while peak return temperature remains within the approved limit.",
                "evidence_support": refs[:4],
                "counterargument": "The baseline packet does not include fan start counts or control commands, and a wider deadband could raise component temperature or merely shift energy to the pump.",
                "disconfirming_observation": "Fan energy or start count does not decline, total cooling energy rises, or temperature variability exceeds the pre-specified tolerance.",
            },
            {
                "statement": "An ambient- and load-aware pump/fan schedule may outperform the fixed baseline settings on cooling energy normalized by delivered thermal load.",
                "prediction": "Across pre-specified ambient bands, total cooling kWh per thermal-load kWh is lower than baseline with no safety or stability threshold breach.",
                "evidence_support": refs[:4],
                "counterargument": "The twelve baseline observations are synthetic, cover only two ambient bands, and do not establish that control settings rather than ambient conditions caused the power difference.",
                "disconfirming_observation": "A blocked or randomized comparison shows no improvement in normalized energy after controlling for ambient temperature and thermal load.",
            },
        ]
    if not seed_hypotheses:
        seed_hypotheses = [
            f"A controlled intervention addressing this goal may change a pre-specified target outcome: {goal or 'unspecified research goal'}."
        ]
    return [
        {
            "statement": statement[:800],
            "prediction": "A pre-specified measurement would differ from a matched baseline if this hypothesis is correct.",
            "evidence_support": refs[:4],
            "counterargument": "The apparent change could be explained by an uncontrolled confounder, measurement error, or an alternative mechanism.",
            "disconfirming_observation": "A controlled test fails to show the predicted difference after checking measurement quality and pre-specified controls.",
        }
        for statement in seed_hypotheses[:3]
    ]


def _normalize_hypotheses(
    candidates: Any, inputs: dict[str, Any], evidence: dict[str, Any]
) -> list[dict[str, Any]]:
    raw = candidates if isinstance(candidates, list) else []
    normalized: list[dict[str, Any]] = []
    for candidate in raw[:3]:
        if not isinstance(candidate, dict):
            continue
        statement = str(candidate.get("statement") or candidate.get("hypothesis") or "").strip()
        if not statement:
            continue
        normalized.append(
            {
                "hypothesis_id": f"H{len(normalized) + 1}",
                "statement": statement[:800],
                "prediction": str(candidate.get("prediction") or "A pre-specified measurement differs from baseline if the hypothesis is correct.")[:800],
                "evidence_support": candidate.get("evidence_support") or list(evidence.get("source_refs") or [])[:4],
                "counterargument": str(candidate.get("counterargument") or "A competing explanation or unmeasured confounder could account for the observation.")[:800],
                "disconfirming_observation": str(candidate.get("disconfirming_observation") or "A controlled test does not show the predicted difference.")[:800],
                "status": "hypothesis_for_review",
            }
        )
    if not normalized:
        normalized = _fallback_hypotheses(inputs, evidence)
        for index, item in enumerate(normalized, start=1):
            item["hypothesis_id"] = f"H{index}"
            item["status"] = "hypothesis_for_review"
    return normalized


def ask_llm_for_research_packet(
    llm: Any, inputs: dict[str, Any], evidence: dict[str, Any], rag: dict[str, Any], posture: dict[str, Any]
) -> dict[str, Any]:
    fallback = {
        **posture,
        "candidate_hypotheses": _fallback_hypotheses(inputs, evidence),
        "tool_requests": [],
        "generated_python": "",
    }
    user = json.dumps(
        {
            "inputs": inputs,
            "deterministic_evidence": evidence,
            "retrieved_context": rag.get("context", ""),
            "review_posture": posture,
        },
        sort_keys=True,
        default=str,
    )
    try:
        response = llm.generate_json(
            system_prompt=load_prompt("research-packet-system.md"),
            user_prompt=f"{load_prompt('research-review-task.md')}\n\n{user}",
            fallback=fallback,
        )
    except Exception:
        response = fallback
    if not isinstance(response, dict):
        response = fallback
    action = str(response.get("recommended_action") or posture["recommended_action"]).lower()
    if action not in RESEARCH_ACTIONS:
        action = posture["recommended_action"]
    confidence = str(response.get("confidence") or posture["confidence"]).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = posture["confidence"]
    return {
        "recommended_action": action,
        "confidence": confidence,
        "rationale": str(response.get("rationale") or posture["rationale"])[:2000],
        "candidate_hypotheses": _normalize_hypotheses(response.get("candidate_hypotheses"), inputs, evidence),
        "tool_requests": response.get("tool_requests") if isinstance(response.get("tool_requests"), list) else [],
        "generated_python": str(response.get("generated_python") or "")[:40000],
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

    The workflow manifest places this function in its only OpenShell node.
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

    recommendation = ask_llm_for_research_packet(llm, inputs, evidence, rag, posture)
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

    autonomous = {
        "schema_version": "mn.blueprint.autonomous_research.v1",
        "isolation_required": True,
        "runner": "openshell",
        "single_job_instance": True,
        "session": session.snapshot(),
        "tool_observations": observations,
        "generated_code_result": code_result,
    }
    return recommendation, autonomous, warnings


def _experiment_concepts(hypotheses: list[dict[str, Any]], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = []
    for hypothesis in hypotheses:
        concepts.append(
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "design_status": "concept_for_human_review",
                "baseline": "Pre-specified matched baseline or control condition.",
                "intervention": hypothesis["statement"],
                "measurements": ["primary outcome", "relevant confounders", "pre-specified safety or quality boundary"],
                "decision_rule": "Compare the pre-specified outcome with the baseline and report uncertainty, sensitivity checks, and deviations.",
                "approval_dependencies": ["qualified human review", *(["scope constraint review"] if inputs.get("constraints") else [])],
                "not_executed": True,
            }
        )
    return concepts


def autonomous_research(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm = research_llm(ctx["config"], actor=True)
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
        context={"inputs": inputs, "evidence": verified_evidence, "recommendation": recommendation, "rag": state.get("rag") or {}, "sources": sources},
    )
    state.update({"inputs": inputs, "evidence": verified_evidence, "posture": deterministic_research_posture(verified_evidence), "recommendation": recommendation, "autonomous": autonomous, "actor_findings": actor_findings, "warnings": [*(state.get("warnings") or []), *autonomous_warnings], "llm_usage": llm_usage(llm)})
    _save(ctx, state)
    return {"tool_calls": (autonomous.get("session") or {}).get("tool_calls_used", 0)}


__all__ = [
    "_document_tool",
    "_experiment_concepts",
    "_fallback_hypotheses",
    "_normalize_hypotheses",
    "_rank_hypotheses_tool",
    "ask_llm_for_research_packet",
    "autonomous_research",
    "run_autonomous_research",
]
