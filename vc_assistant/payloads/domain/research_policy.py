"""VC research planning, fact-table, and source-summary policy."""

from __future__ import annotations

from .common import *
from .evidence import is_substantive_public_source
from .intake import slugify
from .research_core import _configured_research

def _records_text(records: list[dict[str, Any]]) -> str:
    return "\n".join(str(record.get("text_preview") or "") for record in records)

def _extract_public_urls(text: str) -> list[str]:
    urls = []
    for match in re.finditer(r"https?://[^\s<>)\"']+", text, flags=re.I):
        url = match.group(0).rstrip(".,;:]}")
        if url not in urls:
            urls.append(url)
    return urls[:40]

def _url_domain(url: str) -> str:
    return str(url or "").split("//", 1)[-1].split("/", 1)[0].lower()

def _public_terms_from_text(text: str, terms: list[str], limit: int = 8) -> list[str]:
    haystack = text.lower()
    matches = []
    for term in terms:
        pattern = r"\b" + re.escape(term.lower()) + r"\b"
        if re.search(pattern, haystack):
            matches.append(term)
        if len(matches) >= limit:
            break
    return matches

def extract_public_research_signals(records: list[dict[str, Any]]) -> dict[str, Any]:
    text = _records_text(records)
    urls = _extract_public_urls(text)
    domains = extract_domains(text)
    github_urls = [url for url in urls if "github.com/" in url.lower()]
    docs_urls = [
        url for url in urls
        if any(marker in url.lower() for marker in ("docs.", "/docs", "readme", "developer.", "api."))
    ]
    app_store_urls = [url for url in urls if any(domain in _url_domain(url) for domain in APP_STORE_DOMAINS)]
    package_urls = [url for url in urls if any(domain in _url_domain(url) for domain in PACKAGE_DOMAINS)]
    profile_urls = [url for url in urls if any(domain in _url_domain(url) for domain in PROFILE_DOMAINS)]
    public_domains = [
        domain for domain in domains
        if not any(domain.endswith(suffix) for suffix in (".txt", ".pdf", ".csv", ".json"))
    ]
    return {
        "urls": dedupe_list(urls, 40),
        "domains": dedupe_list(public_domains, 20),
        "github_urls": dedupe_list(github_urls, 12),
        "docs_urls": dedupe_list(docs_urls, 12),
        "app_store_urls": dedupe_list(app_store_urls, 8),
        "package_urls": dedupe_list(package_urls, 8),
        "profile_urls": dedupe_list(profile_urls, 12),
        "technical_terms": _public_terms_from_text(text, ["api", "sdk", "github", "open source", "repository", "docs", "developer", "model", "agent", "platform", "infrastructure", "patent", "dataset"]),
        "traction_terms": _public_terms_from_text(text, ["revenue", "arr", "customer", "pilot", "contract", "partnership", "retention", "growth", "launch"]),
        "funding_terms": _public_terms_from_text(text, ["funding", "seed", "pre-seed", "series a", "investor", "accelerator", "venture", "round"]),
        "market_terms": _public_terms_from_text(text, ["market", "tam", "sam", "competitor", "industry", "vertical", "category", "segment"]),
        "pricing_terms": _public_terms_from_text(text, ["pricing", "subscription", "seat", "usage", "gross margin", "payback", "ltv", "cac"]),
        "regulatory_terms": _public_terms_from_text(text, ["hipaa", "soc 2", "soc2", "gdpr", "compliance", "regulatory", "security", "privacy"]),
        "ip_terms": _public_terms_from_text(text, ["patent", "proprietary", "dataset", "model", "ip", "trade secret", "copyright"]),
    }

def _lane(lane_id: str, reason: str, tools: list[str], queries: list[str], target_urls: list[str] | None = None) -> dict[str, Any]:
    lane = shared_lane(lane_id, reason, tools, queries, target_urls)
    lane["queries"] = dedupe_list(lane["queries"], 8)
    return lane

def build_adaptive_research_plan(company: str, records: list[dict[str, Any]], internet: dict[str, Any]) -> dict[str, Any]:
    base = _configured_research(company, internet)
    signals = extract_public_research_signals(records)
    target_urls = list(base["target_urls"])
    target_urls.extend(signals["urls"])
    target_urls.extend(f"https://{domain}" for domain in signals["domains"] if domain not in {"crunchbase.com", "linkedin.com"})
    target_urls = dedupe_list(target_urls, int(internet.get("max_target_urls_per_company") or 10) * 3)
    lanes = [
        _lane(
            "company_identity_research",
            "Always verify company identity, website, founder/profile pages, and basic public footprint.",
            ["web_browser_skill.standard", "web_browser_skill.deep_when_profile_page_is_empty"],
            [f"{company} company website Crunchbase LinkedIn founders", f"{company} founder background company profile"],
            [url for url in target_urls if any(domain in _url_domain(url) for domain in PROFILE_DOMAINS)] or base["target_urls"][:2],
        ),
        _lane(
            "funding_research",
            "Always check funding, investor, accelerator, and press mentions.",
            ["web_browser_skill.standard"],
            [f"{company} startup funding investors accelerator press", f"{company} seed round venture capital investors"],
        ),
        _lane(
            "market_map_research",
            "Map category, market context, competitors, and comparable public companies.",
            ["web_browser_skill.standard"],
            [f"{company} competitors market size comparable companies", f"{company} industry report public company comparables market multiple"],
        ),
        _lane(
            "traction_research",
            "Verify public customer, revenue, partnership, launch, and product traction claims.",
            ["web_browser_skill.standard"],
            [f"{company} customers pilots revenue partnerships product launch", f"{company} customer case study ARR retention growth"],
        ),
    ]
    if signals["github_urls"] or "github" in signals["technical_terms"] or "open source" in signals["technical_terms"]:
        lanes.append(
            _lane(
                "github_research",
                "GitHub or open-source signal was present in the packet; inspect public repo/org activity and technical credibility.",
                ["web_browser_skill.standard", "web_browser_skill.deep_when_page_is_empty"],
                [f"{company} GitHub repository open source stars forks issues releases"],
                signals["github_urls"],
            )
        )
    if signals["docs_urls"] or signals["package_urls"] or signals["app_store_urls"] or signals["technical_terms"]:
        lanes.append(
            _lane(
                "technical_product_research",
                "Technical/product signals were present; inspect docs, package/app footprint, developer surface, and product maturity.",
                ["web_browser_skill.standard", "web_browser_skill.research_topic"],
                [f"{company} API docs SDK developer documentation product", f"{company} app store package release changelog"],
                signals["docs_urls"] + signals["package_urls"] + signals["app_store_urls"],
            )
        )
    if signals["profile_urls"]:
        lanes.append(
            _lane(
                "founder_research",
                "Public profile links were present; inspect founder/company profile pages without using contact details.",
                ["web_browser_skill.standard", "web_browser_skill.deep_when_profile_page_is_empty"],
                [f"{company} founder background public profile"],
                signals["profile_urls"],
            )
        )
    if signals["pricing_terms"]:
        lanes.append(
            _lane(
                "pricing_business_model_research",
                "Pricing or business-model terms were present; look for public pricing, packaging, and monetization evidence.",
                ["web_browser_skill.research_topic"],
                [f"{company} pricing subscription business model revenue model"],
            )
        )
    if signals["regulatory_terms"]:
        lanes.append(
            _lane(
                "regulatory_risk_research",
                "Regulatory or security claims were present; inspect public compliance and risk context.",
                ["web_browser_skill.research_topic"],
                [f"{company} security compliance regulatory privacy SOC 2 GDPR"],
            )
        )
    if signals["ip_terms"]:
        lanes.append(
            _lane(
                "data_ip_defensibility_research",
                "Data, IP, model, or patent terms were present; inspect defensibility and asset evidence.",
                ["web_browser_skill.research_topic"],
                [f"{company} patent proprietary dataset model defensibility"],
            )
        )

    agent_queries = {agent_id: [] for agent_id in RESEARCH_AGENT_IDS}
    agent_target_urls = {agent_id: [] for agent_id in RESEARCH_AGENT_IDS}
    lane_agent = {
        "company_identity_research": "company_identity_researcher",
        "founder_research": "company_identity_researcher",
        "funding_research": "funding_researcher",
        "market_map_research": "market_comp_researcher",
        "competitor_research": "market_comp_researcher",
        "github_research": "market_comp_researcher",
        "technical_product_research": "market_comp_researcher",
        "pricing_business_model_research": "market_comp_researcher",
        "data_ip_defensibility_research": "market_comp_researcher",
        "traction_research": "traction_verifier",
        "regulatory_risk_research": "traction_verifier",
    }
    for lane in lanes:
        agent_id = lane_agent.get(lane["lane_id"])
        if agent_id:
            agent_queries[agent_id].extend(lane["queries"])
            agent_target_urls[agent_id].extend(lane["target_urls"])
    rendered_urls = [
        url for url in target_urls
        if any(domain in _url_domain(url) for domain in JS_HEAVY_DOMAINS)
    ]
    if rendered_urls:
        agent_queries["rendered_page_researcher"].append(f"{company} rendered public profile pages")
    else:
        agent_queries["rendered_page_researcher"].append(f"{company} Crunchbase organization profile rendered page")
    max_queries = int(internet.get("max_queries") or 20)
    for agent_id, queries in list(agent_queries.items()):
        agent_queries[agent_id] = dedupe_list(queries or base["queries"], max_queries)
        agent_target_urls[agent_id] = dedupe_list(agent_target_urls[agent_id], int(internet.get("max_target_urls_per_company") or 10) * 2)

    return {
        **base,
        "adaptive": True,
        "signals": signals,
        "lanes": lanes,
        "agent_queries": agent_queries,
        "agent_target_urls": agent_target_urls,
        "target_urls": target_urls,
        "known_public_urls": target_urls,
        "rendered_target_urls": dedupe_list(rendered_urls or base["target_urls"], int((internet.get("rendered_browser") or {}).get("max_pages_per_company") or 5) * 2),
        "github_urls": signals["github_urls"],
        "privacy_policy": "Queries use company names, public URLs/domains, public categories, and non-confidential public claims only; confidential excerpts, private financials, customer names, and founder contact details are blocked.",
    }

def parse_financial_tool_outputs(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outputs = []
    for source in sources:
        if source.get("skill") != "financial_public_data_tool":
            continue
        try:
            decoded = json.loads(str(source.get("snippet") or "{}"))
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            decoded["source_ref"] = source.get("url")
            outputs.append(decoded)
    return outputs

def method_guidance(method_id: str) -> dict[str, str]:
    guidance = VC_METHOD_GUIDANCE.get(method_id) or {}
    return {
        "label": str(guidance.get("label") or method_id.replace("_", " ").title()),
        "memory_hook": str(guidance.get("memory_hook") or ""),
        "purpose": str(guidance.get("purpose") or "screening evidence review"),
    }

def method_status_reason(
    *,
    method_id: str,
    status: str,
    score: float | int | None,
    inputs_used: list[str],
    source_refs: list[str],
    missing_evidence: list[str],
    assumptions: list[str],
) -> str:
    guidance = method_guidance(method_id)
    evidence_count = len([ref for ref in source_refs if ref])
    input_preview = ", ".join(inputs_used[:4]) if inputs_used else "no named inputs"
    if status == "scored":
        assumption_note = f" Assumptions: {'; '.join(assumptions[:2])}" if assumptions else ""
        return (
            f"{guidance['label']} uses {guidance['purpose']}. "
            f"It produced score {round(score, 2) if isinstance(score, (int, float)) else 'n/a'} "
            f"from {input_preview} with {evidence_count} evidence ref(s).{assumption_note}"
        )
    gap_preview = "; ".join(missing_evidence[:2]) if missing_evidence else "required evidence was not present"
    return (
        f"{guidance['label']} uses {guidance['purpose']}. "
        f"It stayed insufficient_evidence because {gap_preview}."
    )

def build_fact_table(company: str, records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(str(record.get("text_preview") or "") for record in records)
    substantive_sources = [source for source in sources if is_substantive_public_source(source)]
    financial_tool_outputs = parse_financial_tool_outputs(sources)
    source_text = "\n".join(str(source.get("snippet") or "") for source in substantive_sources)
    values = money_values(text)
    source_values = money_values(source_text)
    tool_values = [
        float(value)
        for output in financial_tool_outputs
        for value in output.get("monetary_values", [])
        if isinstance(value, (int, float))
    ]
    comparable_domains = sorted(
        {
            str(domain)
            for output in financial_tool_outputs
            for domain in output.get("comparable_domains", [])
            if domain
        }
    )
    keywords = {
        "team": ["founder", "team", "advisor", "operator", "engineer", "domain expert"],
        "market": ["tam", "sam", "market", "industry", "competition", "segment", "buyer"],
        "traction": ["revenue", "customer", "pilot", "contract", "growth", "retention", "sales"],
        "product": ["prototype", "mvp", "product", "platform", "demo", "patent", "technology"],
        "strategic": ["partner", "channel", "strategic", "distribution", "enterprise", "supplier"],
        "risk": ["risk", "regulatory", "churn", "burn", "competition", "dependency", "lawsuit"],
        "asset": ["built", "patent", "r&d", "dataset", "hardware", "model", "infrastructure"],
    }
    scores = {name: keyword_score(text, terms) for name, terms in keywords.items()}
    source_scores = {name: keyword_score(source_text, terms) for name, terms in keywords.items()}
    return {
        "company_name": company,
        "company_slug": slugify(company),
        "generated_at": utc_now_iso(),
        "team_facts": {
            "score": scores["team"],
            "keywords": keywords["team"],
            "evidence_refs": source_refs_from_records(records),
        },
        "market_facts": {
            "score": max(scores["market"], source_scores["market"]),
            "keywords": keywords["market"],
            "public_source_refs": source_refs_from_sources(substantive_sources),
        },
        "traction_facts": {
            "score": scores["traction"],
            "keywords": keywords["traction"],
            "monetary_values": values,
        },
        "financial_facts": {
            "local_monetary_values": values,
            "public_monetary_values": source_values,
            "tool_monetary_values": tool_values,
            "largest_local_value": max(values) if values else None,
            "largest_public_value": max(source_values + tool_values) if source_values or tool_values else None,
            "largest_relevant_value": max(values + source_values + tool_values) if values or source_values or tool_values else None,
            "financial_tool_outputs": financial_tool_outputs,
        },
        "risk_facts": {
            "score": scores["risk"],
            "keywords": keywords["risk"],
            "warning_terms": [term for term in keywords["risk"] if term in text.lower()],
        },
        "ip_asset_facts": {
            "score": scores["asset"],
            "keywords": keywords["asset"],
        },
        "product_facts": {
            "score": scores["product"],
            "keywords": keywords["product"],
        },
        "relationship_facts": {
            "score": scores["strategic"],
            "keywords": keywords["strategic"],
        },
        "comparable_candidates": {
            "source_count": len(substantive_sources) + len(comparable_domains),
            "domains": extract_domains(text) + [str(source.get("url") or "").split("//", 1)[-1].split("/", 1)[0] for source in substantive_sources[:8]] + comparable_domains,
            "public_source_refs": source_refs_from_sources(substantive_sources) + [str(output.get("source_ref") or "") for output in financial_tool_outputs if output.get("source_ref")],
        },
        "raw_counts": {
            "document_count": len(records),
            "research_source_count": len(sources),
            "substantive_research_source_count": len(substantive_sources),
            "character_count": sum(int(record.get("character_count") or 0) for record in records),
        },
    }

def method_result(*, method_id: str, **values: Any) -> dict[str, Any]:
    """Build a score result using the manifest-owned method-to-agent binding."""

    try:
        scorer_id = SCORER_AGENT_BY_METHOD[method_id]
    except KeyError as exc:
        raise ValueError(f"unknown valuation method: {method_id}") from exc
    return shared_method_result(
        method_id=method_id,
        scorer_id=scorer_id,
        guidance_resolver=method_guidance,
        status_reason_builder=method_status_reason,
        evidence_summary_defaults={"judge_rubric": JUDGE_RUBRIC},
        include_descriptors=False,
        **values,
    )
