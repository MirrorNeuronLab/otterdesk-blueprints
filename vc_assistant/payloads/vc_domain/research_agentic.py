"""LLM-guided public-research decision loop for VC research agents."""

from __future__ import annotations

from .common import *
from .intake import slugify
from .knowledge import (
    RESEARCH_AGENT_PROMPT_FILES,
    citation_ref_values,
    knowledge_rag_is_required,
    load_prompt,
    prompt_spec_from_markdown,
    rag_ref_values,
    require_ready_rag,
    retrieve_knowledge_rag_context,
    validate_llm_rag_refs,
)
from .research_core import (
    _agent_tool_source,
    _default_agent_tool_response,
    _execute_agent_tool_plan,
    _research_agent_plan_record,
)
from .runtime_tools import append_observation_record

def research_prompt_spec(agent_id: str) -> dict[str, Any]:
    return prompt_spec_from_markdown(RESEARCH_AGENT_PROMPT_FILES.get(agent_id, RESEARCH_AGENT_PROMPT_FILES["research_planner"]))

def build_research_agent_prompt(
    *,
    company: str,
    agent_id: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    allowed_tools: set[str],
    remaining_tool_calls: int,
    rag_context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
    observations: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    spec = research_prompt_spec(agent_id)
    system_prompt = load_prompt(
        "research-agent-system.md",
        agent_id=agent_id,
        mission=spec["mission"],
    )
    return system_prompt, {
        "task": load_prompt("research-agent-task.md"),
        "company": company,
        "agent_id": agent_id,
        "mission": spec["mission"],
        "allowed_evidence": spec["allowed_evidence"],
        "forbidden_inputs": spec["forbidden_inputs"],
        "rag_query_terms": spec["rag_query_terms"],
        "tool_policy": spec["tool_policy"],
        "failure_conditions": spec["failure_conditions"],
        "privacy_policy": plan.get("privacy_policy"),
        "allowed_tools": sorted(allowed_tools),
        "remaining_tool_calls": remaining_tool_calls,
        "rag_refs_required": knowledge_rag_is_required(knowledge_rag),
        "knowledge_rag": {
            "status": rag_context.get("status"),
            "context": rag_context.get("context"),
            "citations": rag_context.get("citations"),
        },
        "adaptive_plan": {
            "lanes": plan.get("lanes", []),
            "agent_queries": (plan.get("agent_queries") or {}).get(agent_id, []),
            "agent_target_urls": (plan.get("agent_target_urls") or {}).get(agent_id, []),
            "rendered_target_urls": plan.get("rendered_target_urls", []),
            "signals": plan.get("signals", {}),
        },
        "observations": observations[-8:],
        "required_schema": {
            "thought_summary": "short non-sensitive rationale",
            "tool_calls": [
                {
                    "tool": "browser_search|browser_page|rendered_browser_page|finish",
                    "query": "optional public-safe query",
                    "url": "optional public URL",
                    "reason": "optional reason tied to mission",
                    "rag_refs": ["citation ref numbers used to choose this action"],
                }
            ],
            "evidence_gaps": ["specialist evidence gaps"],
            "rag_refs": ["top-level citation ref numbers used"],
            "stop_reason": "optional",
        },
    }

def build_research_agent_rag_query(*, agent_id: str, plan: dict[str, Any]) -> str:
    spec = research_prompt_spec(agent_id)
    agent_queries = (plan.get("agent_queries") or {}).get(agent_id, []) if isinstance(plan.get("agent_queries"), dict) else []
    if not agent_queries:
        agent_queries = plan.get("queries") or []
    lane_ids = [
        str(lane.get("lane_id") or "")
        for lane in plan.get("lanes", [])[:8]
        if isinstance(lane, dict) and lane.get("lane_id")
    ]
    parts = [
        agent_id,
        spec["mission"],
        " ".join(spec["rag_query_terms"]),
        " ".join(lane_ids),
        " ".join(str(query) for query in agent_queries[:3]),
    ]
    return " ".join(part for part in parts if part).strip()

def run_agentic_research_agent(
    *,
    company: str,
    agent_id: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    action_budget: ActionBudget | None,
    llm: Any,
    agentic: dict[str, Any],
    trace: list[dict[str, Any]] | None,
    knowledge_rag: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    queries = (plan.get("agent_queries") or {}).get(agent_id, []) or plan.get("queries") or []
    sources = [_research_agent_plan_record(company, agent_id, item, plan) for item in queries]
    allowed_tools = set(agentic.get("allowed_tools") or DEFAULT_AGENTIC_RESEARCH_TOOLS)
    max_iterations = int(agentic.get("max_iterations_per_agent") or 20)
    max_tool_calls = int(agentic.get("max_tool_calls_per_agent") or 50)
    agent_operation_id = f"agentic-research-{slugify(agent_id)}-{uuid.uuid4().hex[:8]}"
    agent_started = time.monotonic()
    append_observation_record(
        run_dir,
        "observability_operation_started",
        {
            "operation_id": agent_operation_id,
            "phase": "agentic_research",
            "operation": agent_id,
            "status": "started",
            "company": company,
            "agent_id": agent_id,
            "max_iterations": max_iterations,
            "max_tool_calls": max_tool_calls,
        },
    )
    rag_query = build_research_agent_rag_query(agent_id=agent_id, plan=plan)
    rag_context = retrieve_knowledge_rag_context(knowledge_rag=knowledge_rag, query=rag_query, stage=agent_id, company=company, run_dir=run_dir)
    require_ready_rag(knowledge_rag, stage=agent_id, company=company, context=rag_context, min_citations=1, run_dir=run_dir)
    observations: list[dict[str, Any]] = []
    executed_tool_calls = 0
    trace_record = {
        "agent_id": agent_id,
        "company": company,
        "enabled": True,
        "max_iterations": max_iterations,
        "max_tool_calls": max_tool_calls,
        "allowed_tools": sorted(allowed_tools),
        "iterations": [],
        "validation_failures": [],
        "stop_reason": "",
        "budget_start": action_budget.summary(include_actions=False) if action_budget else {},
        "budget_end": {},
        "rag_context": {
            "enabled": rag_context.get("enabled"),
            "status": rag_context.get("status"),
            "query": rag_context.get("query"),
            "citation_count": len(rag_context.get("citations") or []),
            "context_chars": len(str(rag_context.get("context") or "")),
        },
        "knowledge_refs": rag_context.get("citations") or [],
    }
    for iteration in range(1, max_iterations + 1):
        if executed_tool_calls >= max_tool_calls:
            trace_record["stop_reason"] = "max_tool_calls_reached"
            break
        fallback = _default_agent_tool_response(agent_id, plan, observations)
        system_prompt, prompt = build_research_agent_prompt(
            company=company,
            agent_id=agent_id,
            plan=plan,
            internet=internet,
            allowed_tools=allowed_tools,
            remaining_tool_calls=max_tool_calls - executed_tool_calls,
            rag_context=rag_context,
            knowledge_rag=knowledge_rag,
            observations=observations,
        )
        try:
            decision = llm.generate_json(system_prompt=system_prompt, user_prompt=json.dumps(prompt, default=str), fallback=fallback)
        except Exception as exc:
            message = f"Agent tool loop failed: {exc}"
            sources.append(_agent_tool_source(company=company, agent_id=agent_id, query=queries[0] if queries else "", status="agent_tool_loop_failed", message=message))
            trace_record["iterations"].append({"iteration": iteration, "status": "failed", "error": str(exc)})
            trace_record["stop_reason"] = "agent_tool_loop_failed"
            break
        if isinstance(decision, dict) and decision.get("provider") == "budget_exhausted":
            message = "Agent tool loop stopped because the action budget was exhausted before the LLM could choose tools."
            sources.append(_agent_tool_source(company=company, agent_id=agent_id, query=queries[0] if queries else "", status="budget_exhausted", message=message))
            trace_record["iterations"].append({"iteration": iteration, "status": "budget_exhausted"})
            trace_record["stop_reason"] = "budget_exhausted"
            break
        if not isinstance(decision, dict):
            message = "Agent returned non-object JSON for tool decision."
            sources.append(_agent_tool_source(company=company, agent_id=agent_id, query=queries[0] if queries else "", status="agent_invalid_tool_call", message=message))
            trace_record["iterations"].append({"iteration": iteration, "status": "invalid_response", "response_type": type(decision).__name__})
            trace_record["stop_reason"] = "agent_invalid_tool_call"
            break
        if knowledge_rag_is_required(knowledge_rag) and not rag_ref_values(decision):
            refs = citation_ref_values(rag_context)
            if refs:
                decision["rag_refs"] = refs
                decision.setdefault("evidence_gaps", [])
                if isinstance(decision["evidence_gaps"], list):
                    decision["evidence_gaps"].append("Agent omitted explicit RAG refs; refs were attached from retrieved stage context.")
        try:
            validate_llm_rag_refs(decision, knowledge_rag=knowledge_rag, stage=agent_id, company=company)
        except Exception as exc:
            sources.append(_agent_tool_source(company=company, agent_id=agent_id, query=queries[0] if queries else "", status="agent_invalid_tool_call", message=str(exc)))
            trace_record["iterations"].append({"iteration": iteration, "status": "invalid_rag_refs", "error": str(exc)})
            trace_record["stop_reason"] = "required_rag_refs_missing"
            trace_record["budget_end"] = action_budget.summary(include_actions=False) if action_budget else {}
            if trace is not None:
                trace.append(trace_record)
            append_observation_record(
                run_dir,
                "observability_operation_failed",
                {
                    "operation_id": agent_operation_id,
                    "phase": "agentic_research",
                    "operation": agent_id,
                    "status": "failed",
                    "company": company,
                    "agent_id": agent_id,
                    "error": str(exc),
                    "elapsed_ms": round((time.monotonic() - agent_started) * 1000, 2),
                },
            )
            raise
        tool_calls = decision.get("tool_calls") if isinstance(decision.get("tool_calls"), list) else []
        iteration_record = {
            "iteration": iteration,
            "thought_summary": str(decision.get("thought_summary") or "")[:500],
            "requested_tool_calls": tool_calls,
            "executed_tool_calls": [],
            "observations": [],
            "stop_reason": str(decision.get("stop_reason") or ""),
            "evidence_gaps": list(decision.get("evidence_gaps") or [])[:10] if isinstance(decision.get("evidence_gaps"), list) else [],
        }
        if not tool_calls:
            message = "Agent returned no tool calls."
            sources.append(_agent_tool_source(company=company, agent_id=agent_id, query=queries[0] if queries else "", status="agent_invalid_tool_call", message=message))
            trace_record["validation_failures"].append({"iteration": iteration, "message": message})
            iteration_record["stop_reason"] = "agent_invalid_tool_call"
            trace_record["iterations"].append(iteration_record)
            trace_record["stop_reason"] = "agent_invalid_tool_call"
            break
        finished = False
        plan_execution = _execute_agent_tool_plan(
            sources=sources,
            company=company,
            stage=agent_id,
            plan=plan,
            internet=internet,
            run_dir=run_dir,
            action_budget=action_budget,
            iteration=iteration,
            decision=decision,
            tool_calls=tool_calls,
            allowed_tools=allowed_tools,
            remaining_tool_calls=max_tool_calls - executed_tool_calls,
        )
        trace_record["validation_failures"].extend(plan_execution["validation_failures"])
        iteration_record["executed_tool_calls"].extend(plan_execution["executed_tool_calls"])
        iteration_record["observations"].extend(plan_execution["observations"])
        iteration_record["bounded_trace"] = plan_execution["bounded_trace"]
        observations.extend(plan_execution["observations"])
        executed_tool_calls += int(plan_execution["tool_call_count"])
        finished = bool(plan_execution["finished"])
        if plan_execution["stop_reason"] in {"max_tool_calls_reached", "agent_invalid_tool_call"}:
            trace_record["stop_reason"] = plan_execution["stop_reason"]
        trace_record["iterations"].append(iteration_record)
        if trace_record.get("stop_reason") == "max_tool_calls_reached":
            break
        if finished:
            trace_record["stop_reason"] = str(decision.get("stop_reason") or "finish")
            break
    if not trace_record["stop_reason"]:
        trace_record["stop_reason"] = "max_iterations_reached"
    trace_record["tool_call_count"] = executed_tool_calls
    trace_record["budget_end"] = action_budget.summary(include_actions=False) if action_budget else {}
    if trace is not None:
        trace.append(trace_record)
    append_observation_record(
        run_dir,
        "observability_operation_completed",
        {
            "operation_id": agent_operation_id,
            "phase": "agentic_research",
            "operation": agent_id,
            "status": "completed",
            "company": company,
            "agent_id": agent_id,
            "stop_reason": trace_record["stop_reason"],
            "tool_call_count": executed_tool_calls,
            "elapsed_ms": round((time.monotonic() - agent_started) * 1000, 2),
            "budget_end": trace_record["budget_end"],
        },
    )
    return agent_id, sources

