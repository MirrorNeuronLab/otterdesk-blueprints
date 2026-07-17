"""VC research-agent execution, joins, and reconciliation."""

from __future__ import annotations

from .common import *
from .evidence import is_substantive_public_source
from .research_agentic import run_agentic_research_agent
from .research_browser import (
    _append_browser_research,
    _append_rendered_browser_research,
    _append_target_url_research,
)
from .research_core import (
    _budget_exhausted_source,
    _research_agent_plan_record,
    _research_agent_enabled,
    _source_record,
    agentic_research_config,
)
from .research_policy import build_adaptive_research_plan
from .runtime_tools import observed_operation

def research_company(company: str, config: dict[str, Any], run_dir: Path | None = None, action_budget: ActionBudget | None = None, records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if internet.get("enabled") is False:
        return []
    plan = build_adaptive_research_plan(company, records or [], internet)
    sources: list[dict[str, Any]] = [
        _source_record(
            company=company,
            query=query,
            url="research_plan",
            title="Privacy-safe research query",
            snippet=f"Verification fields: {', '.join(plan['verification_fields'])}",
            status="planned",
            skill="research_planner",
            verification_target="query_plan",
        )
        for query in plan["queries"]
    ]
    call_with_supported_kwargs(_append_browser_research, sources=sources, company=company, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
    call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
    call_with_supported_kwargs(_append_rendered_browser_research, sources=sources, company=company, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
    for url in list(internet.get("default_source_urls") or DEFAULT_RESEARCH_SOURCE_URLS):
        sources.append(
            _source_record(
                company=company,
                query=plan["queries"][0],
                url=url,
                title=url.split("//", 1)[-1].split("/", 1)[0],
                snippet="Reference source configured for market-size, small-business, public-company, or labor-market context.",
                status="configured_reference",
                skill="research_planner",
                verification_target="market_context",
            )
        )
    return sources

def _research_agent_default_source_record(company: str, agent_id: str, query: str, url: str) -> dict[str, Any]:
    return _source_record(
        company=company,
        query=query,
        url=url,
        title=url.split("//", 1)[-1].split("/", 1)[0],
        snippet="Configured public reference for this research agent; live browser runs can replace or supplement this source.",
        status="configured_reference",
        skill="web_browser_skill",
        verification_target=agent_id,
    )

def _research_agent_plan_with_targets(plan: dict[str, Any], agent_id: str, queries: list[str]) -> dict[str, Any]:
    agent_plan = dict(plan)
    agent_plan["queries"] = [queries[0]]
    agent_urls = (plan.get("agent_target_urls") or {}).get(agent_id) or []
    if agent_id == "rendered_page_researcher":
        agent_urls = plan.get("rendered_target_urls") or agent_urls or plan.get("target_urls") or []
    agent_plan["target_urls"] = dedupe_list(agent_urls or plan.get("target_urls") or [], 30)
    return agent_plan

def _run_research_agent(company: str, agent_id: str, query: str | list[str], plan: dict[str, Any], internet: dict[str, Any], run_dir: Path | None, action_budget: ActionBudget | None = None) -> tuple[str, list[dict[str, Any]]]:
    queries = query if isinstance(query, list) else [query]
    sources = [_research_agent_plan_record(company, agent_id, item, plan) for item in queries]
    agent_plan = _research_agent_plan_with_targets(plan, agent_id, queries)

    if agent_id == "company_identity_researcher":
        identity_internet = dict(internet)
        identity_internet["source_url_templates"] = [
            "https://www.crunchbase.com/organization/{company_slug}",
            "https://www.linkedin.com/company/{company_slug}",
        ]
        identity_plan = _research_agent_plan_with_targets(plan, agent_id, queries)
        identity_plan["target_urls"] = dedupe_list(identity_plan.get("target_urls", []) + [
            template.format(company=company, company_slug=plan["company_slug"])
            for template in identity_internet["source_url_templates"]
        ], 30)
        for item in queries:
            identity_plan["queries"] = [item]
            call_with_supported_kwargs(_append_browser_research, sources=sources, company=company, plan=identity_plan, internet=identity_internet, run_dir=run_dir, verification_target=agent_id, action_budget=action_budget)
        call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=identity_plan, internet=identity_internet, run_dir=run_dir, action_budget=action_budget)
    elif agent_id in {"funding_researcher", "market_comp_researcher", "traction_verifier"}:
        for item in queries:
            agent_plan["queries"] = [item]
            call_with_supported_kwargs(_append_browser_research, sources=sources, company=company, plan=agent_plan, internet=internet, run_dir=run_dir, verification_target=agent_id, action_budget=action_budget)
        if agent_plan.get("target_urls"):
            call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=agent_plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
        for url in list(internet.get("default_source_urls") or DEFAULT_RESEARCH_SOURCE_URLS):
            sources.append(_research_agent_default_source_record(company, agent_id, queries[0], url))
    elif agent_id == "rendered_page_researcher":
        call_with_supported_kwargs(_append_rendered_browser_research, sources=sources, company=company, plan=agent_plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
        if len(sources) == 1:
            sources.append(
                _source_record(
                    company=company,
                    query=queries[0],
                    url="web_browser_skill",
                    title="Rendered browser fallback disabled",
                    snippet="Set internet_research.rendered_browser.enabled=true to inspect JavaScript-rendered public profiles when needed.",
                    status="disabled",
                    skill="web_browser_skill",
                    verification_target=agent_id,
                )
            )
    return agent_id, sources

def _research_agent_needs_deterministic_gap_fill(sources: list[dict[str, Any]]) -> bool:
    if any(is_substantive_public_source(source) for source in sources):
        return False
    return any(str(source.get("status") or "") in {"planned", "warning", "failed", "blocked", "skill_unavailable", "agent_tool_loop_failed", "agent_invalid_tool_call"} for source in sources)

def _with_agentic_gap_fill(
    *,
    company: str,
    agent_id: str,
    sources: list[dict[str, Any]],
    query: str | list[str],
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    action_budget: ActionBudget | None,
) -> tuple[str, list[dict[str, Any]]]:
    if not _research_agent_needs_deterministic_gap_fill(sources):
        return agent_id, sources
    _, fallback_sources = _run_research_agent(company, agent_id, query, plan, internet, run_dir, action_budget)
    for source in fallback_sources:
        source["fallback_after_agentic"] = True
    return agent_id, [*sources, *fallback_sources]

def research_company_with_agents(
    company: str,
    config: dict[str, Any],
    run_dir: Path | None = None,
    action_budget: ActionBudget | None = None,
    records: list[dict[str, Any]] | None = None,
    llm: Any | None = None,
    agent_tool_trace: list[dict[str, Any]] | None = None,
    knowledge_rag: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if internet.get("enabled") is False:
        return {agent_id: [] for agent_id in RESEARCH_AGENT_IDS}
    plan = build_adaptive_research_plan(company, records or [], internet)
    agentic = agentic_research_config(config)
    agent_queries = plan["agent_queries"]
    planner_sources: list[dict[str, Any]] = []
    if llm is not None and _research_agent_enabled(agentic, "research_planner"):
        _, planner_sources = run_agentic_research_agent(
            company=company,
            agent_id="research_planner",
            plan=plan,
            internet=internet,
            run_dir=run_dir,
            action_budget=action_budget,
            llm=llm,
            agentic=agentic,
            trace=agent_tool_trace,
            knowledge_rag=knowledge_rag,
        )
    worker_count = bounded_int(internet.get("max_parallel_research_agents"), default=min(5, len(agent_queries)), maximum=len(agent_queries))
    if worker_count <= 1:
        results = [
            (
                run_agentic_research_agent(
                    company=company,
                    agent_id=agent_id,
                    plan=plan,
                    internet=internet,
                    run_dir=run_dir,
                    action_budget=action_budget,
                    llm=llm,
                    agentic=agentic,
                    trace=agent_tool_trace,
                    knowledge_rag=knowledge_rag,
                )
                if llm is not None and _research_agent_enabled(agentic, agent_id)
                else _run_research_agent(company, agent_id, query, plan, internet, run_dir, action_budget)
            )
            for agent_id, query in agent_queries.items()
        ]
    else:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="vc-research") as executor:
            futures = {
                (
                    executor.submit(
                        run_agentic_research_agent,
                        company=company,
                        agent_id=agent_id,
                        plan=plan,
                        internet=internet,
                        run_dir=run_dir,
                        action_budget=action_budget,
                        llm=llm,
                        agentic=agentic,
                        trace=agent_tool_trace,
                        knowledge_rag=knowledge_rag,
                    )
                    if llm is not None and _research_agent_enabled(agentic, agent_id)
                    else executor.submit(_run_research_agent, company, agent_id, query, plan, internet, run_dir, action_budget)
                ): agent_id
                for agent_id, query in agent_queries.items()
            }
            results = [future.result() for future in as_completed(futures)]
    normalized_results = []
    for agent_id, agent_sources in results:
        if llm is not None and _research_agent_enabled(agentic, agent_id):
            normalized_results.append(
                _with_agentic_gap_fill(
                    company=company,
                    agent_id=agent_id,
                    sources=agent_sources,
                    query=agent_queries.get(agent_id, []),
                    plan=plan,
                    internet=internet,
                    run_dir=run_dir,
                    action_budget=action_budget,
                )
            )
        else:
            normalized_results.append((agent_id, agent_sources))
    results = normalized_results
    by_agent = {agent_id: sources for agent_id, sources in results}
    if planner_sources:
        by_agent["company_identity_researcher"] = planner_sources + by_agent.get("company_identity_researcher", [])
    return {agent_id: by_agent.get(agent_id, []) for agent_id in RESEARCH_AGENT_IDS}

def append_financial_tool_research(
    company: str,
    records: list[dict[str, Any]],
    research_ledger: dict[str, list[dict[str, Any]]],
    action_budget: ActionBudget | None = None,
    run_dir: Path | None = None,
) -> None:
    source_count_start = sum(len(items) for items in research_ledger.values())
    tool_status = "completed"
    tool_error = ""
    op = observed_operation(
        run_dir,
        phase="public_tool_call",
        operation="local_public_financial_tool",
        tool="local_public_financial_tool",
        company=company,
    ).__enter__()
    try:
        append_financial_tool_research_unobserved(company, records, research_ledger, action_budget=action_budget)
        new_sources = flattened_sources(research_ledger)[source_count_start:]
        if new_sources:
            statuses = {str(source.get("status") or "") for source in new_sources if source.get("status")}
            if "warning" in statuses:
                tool_status = "warning"
            tool_error = "; ".join(str(source.get("warning") or "") for source in new_sources if source.get("warning"))[:500]
    except Exception as exc:
        tool_status = "failed"
        tool_error = str(exc)
        raise
    finally:
        op.close(
            "completed" if tool_status in {"completed", "ok", ""} else "failed",
            tool_status=tool_status,
            source_count=sum(len(items) for items in research_ledger.values()) - source_count_start,
            error=tool_error,
        )

def append_financial_tool_research_unobserved(
    company: str,
    records: list[dict[str, Any]],
    research_ledger: dict[str, list[dict[str, Any]]],
    action_budget: ActionBudget | None = None,
) -> None:
    action = action_budget.start(
        action_type="financial_tool",
        stage="comparables_market_multiple_scorer",
        company=company,
        tool="local_public_financial_tool",
        metadata={"adapter": "deterministic_public_comparable_and_exit_math"},
    ) if action_budget else None
    if action_budget and action is None:
        research_ledger.setdefault("market_comp_researcher", []).append(
            _budget_exhausted_source(company, f"{company} financial tool comparables", "financial_public_data_tool", "financial_tool_comparables", "financial_tool")
        )
        return

    local_text = "\n".join(str(record.get("text_preview") or "") for record in records)
    sources = flattened_sources(research_ledger)
    substantive_sources = [source for source in sources if is_substantive_public_source(source)]
    monetary_values = money_values(local_text)
    public_values = money_values("\n".join(str(source.get("snippet") or "") for source in substantive_sources))
    comparable_domains = []
    for domain in extract_domains(local_text):
        if domain not in comparable_domains:
            comparable_domains.append(domain)
    for source in substantive_sources:
        domain = str(source.get("url") or "").split("//", 1)[-1].split("/", 1)[0]
        if domain and domain not in comparable_domains:
            comparable_domains.append(domain)

    traction_terms = keyword_score(local_text, ["revenue", "customer", "pilot", "contract", "growth", "retention", "sales"])
    market_terms = keyword_score(local_text + "\n".join(str(source.get("snippet") or "") for source in substantive_sources), ["market", "tam", "sam", "competitor", "industry"])
    tool_output = {
        "tool": "local_public_financial_tool",
        "status": "ok" if monetary_values or public_values or comparable_domains else "insufficient_evidence",
        "monetary_values": monetary_values + public_values,
        "largest_monetary_value": max(monetary_values + public_values) if monetary_values or public_values else None,
        "comparable_domains": comparable_domains[:12],
        "revenue_multiple_range": [3, 8] if traction_terms >= 25 and market_terms >= 25 else [1, 3],
        "exit_value_multiple": 8,
        "required_return_multiple": 10,
        "source_refs": source_refs_from_records(records) + source_refs_from_sources(substantive_sources),
        "missing_evidence": [],
    }
    if not monetary_values and not public_values:
        tool_output["missing_evidence"].append("No local or public monetary value was available for valuation math.")
    if not comparable_domains:
        tool_output["missing_evidence"].append("No comparable company domains were available from local documents or substantive public sources.")
    if not substantive_sources:
        tool_output["missing_evidence"].append("No substantive public market or comparable sources were collected before the financial tool ran.")

    status = "ok" if tool_output["status"] == "ok" else "warning"
    research_ledger.setdefault("market_comp_researcher", []).append(
        _source_record(
            company=company,
            query=f"{company} deterministic financial comparable and exit heuristics",
            url="financial_tool://local_public_comparable_and_exit_math",
            title="Financial Tool: Comparable And Exit Heuristics",
            snippet=json.dumps(tool_output, sort_keys=True),
            status=status,
            skill="financial_public_data_tool",
            verification_target="financial_tool_comparables",
            warning="; ".join(tool_output["missing_evidence"]),
        )
    )
    if action_budget:
        action_budget.complete(action, "completed", {"status": tool_output["status"], "missing_evidence_count": len(tool_output["missing_evidence"])})

def reconcile_research(records: list[dict[str, Any]], research_ledger: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    local_text = "\n".join(str(record.get("text_preview") or "") for record in records).lower()
    all_sources = flattened_sources(research_ledger)
    confirmations = []
    conflicts = []
    missing = []
    for topic, terms in {
        "team": ["founder", "team"],
        "traction": ["customer", "revenue", "pilot"],
        "product": ["product", "prototype", "mvp"],
        "market": ["market", "competitor"],
    }.items():
        local_has = any(term in local_text for term in terms)
        public_has = any(any(term in str(source.get("snippet") or "").lower() for term in terms) for source in all_sources)
        if local_has and public_has:
            confirmations.append(topic)
        elif local_has and not public_has:
            missing.append({"topic": topic, "message": "Local claim was not confirmed by public research snippets."})
    for source in all_sources:
        status = str(source.get("status") or "")
        if status in {"blocked", "failed", "skill_unavailable"}:
            conflicts.append({"source": source.get("url"), "status": status, "message": source.get("warning") or source.get("snippet")})
    return {
        "confirmations": confirmations,
        "conflicts": conflicts,
        "missing_public_evidence": missing,
        "source_count": len(all_sources),
        "reconciled_at": utc_now_iso(),
    }
