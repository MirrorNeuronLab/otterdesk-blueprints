"""Privacy-safe public research, deterministic comparison, and bounded LLM review."""

from __future__ import annotations

import inspect
import json
import re
from typing import Any

from .common import _compact, _now, _sha256, load_prompt
from .inputs import _call_optional


def build_public_queries(inputs: dict[str, Any], intake_plan: dict[str, Any] | None = None) -> list[str]:
    intake_plan = intake_plan if isinstance(intake_plan, dict) else {}
    subject = _public_query_subject(inputs)
    if not subject:
        return []
    location = sanitize_public_text(inputs.get("location", ""))
    budget = _number(inputs.get("budget"))
    budget_term = f"under ${budget:,.0f}" if budget is not None else ""
    constraint_terms = _public_constraint_terms(inputs.get("constraints"))
    plan_topics = [
        sanitize_public_text(item)
        for item in intake_plan.get("public_query_topics") or []
        if sanitize_public_text(item)
    ][:2]
    topics = {
        "property": [
            "current listings comparable sales property tax insurance inspection",
            "ownership cost maintenance financing closing costs resale risk",
        ],
        "rental_property": [
            "current rent comparable listings lease terms deposit availability",
            "operating cost insurance maintenance vacancy tenant risk",
        ],
        "car": [
            "current dealer price availability warranty recalls",
            "five year ownership cost tax registration insurance maintenance resale value",
        ],
        "airline_ticket": [
            "current fare availability baggage seat fees",
            "cancellation change policy schedule reliability total trip cost",
        ],
        "computer": [
            "official specifications GPU memory CPU RAM storage power requirements",
            "three year total cost electricity reliability repair downtime support resale value",
        ],
        "custom": [
            "current market price availability warranty support",
            "total ownership cost maintenance reliability exit value supplier risk",
        ],
    }
    market_query = " ".join(
        part for part in (subject, location, "current price in stock comparable alternatives", budget_term) if part
    )
    selected = [market_query]
    for topic in [*topics.get(inputs.get("purchase_type"), topics["custom"]), *plan_topics]:
        query = " ".join(part for part in (subject, topic, constraint_terms) if part)
        if query not in selected:
            selected.append(query)
    return [query[:240].strip() for query in selected if query.strip()][:4]


def _public_query_subject(inputs: dict[str, Any]) -> str:
    category = str(inputs.get("purchase_type") or "").strip().lower()
    description = sanitize_public_text(inputs.get("item_description", ""))
    lowered = description.lower().replace("-", " ")
    if category == "computer":
        purpose = "local AI " if "local ai" in lowered or "machine learning" in lowered else ""
        form = "desktop workstation" if "desktop" in lowered or "workstation" in lowered else "computer"
        return f"{purpose}{form}".strip()
    words = description.split()
    return " ".join(words[:14]) or sanitize_public_text(category)


def _public_constraint_terms(raw_constraints: Any) -> str:
    constraints = raw_constraints if isinstance(raw_constraints, dict) else {}
    labels = {
        "min_gpu_vram_gb": "GB GPU VRAM",
        "min_system_ram_gb": "GB RAM",
        "min_storage_tb": "TB storage",
        "min_warranty_years": "year warranty",
    }
    terms = []
    for key, suffix in labels.items():
        value = _number(constraints.get(key))
        if value is not None:
            formatted = f"{value:g}"
            terms.append(f"{formatted}{suffix}" if suffix.startswith("GB") or suffix.startswith("TB") else f"{formatted} {suffix}")
    return " ".join(terms)


def sanitize_public_text(value: Any) -> str:
    text = str(value or "")
    blocked = (
        "raw_document_text",
        "private_financial",
        "private financial",
        "account number",
        "account_number",
        "password",
        "ssn",
        "confidential",
        "contact details",
        "customer name",
        "email",
        "phone",
    )
    lowered = text.lower()
    if any(marker in lowered for marker in blocked):
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"[^\w\s.,:/-]", "", text)[:180]


def _load_web_browser_skill() -> tuple[Any, Any, Any]:
    try:
        from mn_web_browser_skill import WebBrowserConfig, browse, research_topic
        return WebBrowserConfig, browse, research_topic
    except Exception:
        return None, None, None


def _source_record(*, url: str, title: str, snippet: str, status: str, skill: str, query: str, warning: str = "") -> dict[str, Any]:
    lowered = f"{title} {snippet} {warning}".lower()
    if any(marker in lowered for marker in ("captcha", "login required", "robots.txt", "access denied", "blocked")):
        status = "blocked"
    elif status == "ok":
        status = "observed"
    return {
        "source_ref": f"web:{_sha256(url or query)[:12]}",
        "url": url,
        "title": title or url or skill,
        "snippet": snippet[:1800],
        "status": status,
        "skill": skill,
        "query": query,
        "retrieved_at": _now(),
        "warning": warning,
    }


def _normalize_browser_result(result: Any, query: str, skill: str) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        candidates = [result]
        for collection_key in ("sources", "results", "items"):
            if collection_key in result:
                collection = result.get(collection_key)
                candidates = collection if isinstance(collection, list) else []
                break
    elif isinstance(result, list):
        candidates = result
    else:
        candidates = [{"text": str(result or "")}] if result else []
    records = []
    for item in candidates:
        if isinstance(item, str):
            item = {"text": item}
        item_warnings = item.get("warnings") or []
        if isinstance(item_warnings, str):
            item_warnings = [item_warnings]
        warning = str(
            item.get("warning")
            or item.get("error")
            or item.get("block_reason")
            or "; ".join(str(value) for value in item_warnings if value)
            or ""
        )
        records.append(_source_record(
            url=str(item.get("final_url") or item.get("url") or item.get("link") or ""),
            title=str(item.get("title") or item.get("name") or ""),
            snippet=str(item.get("snippet") or item.get("text") or item.get("content") or ""),
            status=str(item.get("status") or "observed"),
            skill=skill,
            query=query,
            warning=warning,
        ))
    return records


def research_public_sources(
    queries: list[str],
    config: dict[str, Any],
    *,
    seed_urls: list[str] | None = None,
    quick_test: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if not internet.get("enabled", True):
        return [], [{"status": "disabled", "message": "Public research is disabled by configuration."}]
    if quick_test:
        return [], [{"status": "skipped_quick_test", "message": "Public research is skipped in fake/quick-test mode."}]
    sources: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    max_queries = max(0, min(8, int(internet.get("max_queries", 2))))
    max_seed_urls = max(0, min(12, int(internet.get("max_seed_urls", 6))))
    max_sources = max(1, min(8, int(internet.get("max_sources", 3))))
    browser_config_cls, browse, research_topic = _load_web_browser_skill()
    raw_config = {
        "timeout_seconds": internet.get("timeout_seconds", 20),
        "total_timeout_seconds": internet.get("total_timeout_seconds", 60),
        "max_chars": internet.get("max_chars", 12000),
        "output_format": "plain_text",
        "respect_robots": internet.get("respect_robots", True),
        "per_host_delay_seconds": internet.get("per_host_delay_seconds", 1),
    }
    browser_config = _instantiate(browser_config_cls, raw_config)
    for url in list(dict.fromkeys(seed_urls or []))[:max_seed_urls]:
        if browse is None:
            warnings.append(
                {
                    "status": "skill_unavailable",
                    "skill": "web_browser_skill",
                    "url": url,
                    "message": "The supplied public research link could not be opened because the unified web browser skill is unavailable.",
                }
            )
            break
        try:
            result = _call_optional(
                browse,
                url=url,
                config=browser_config,
                depth="standard",
                output_format="plain_text",
            )
            records = _normalize_browser_result(
                result,
                "User-supplied public research lead",
                "web_browser_skill",
            )
            for record in records:
                if not record["url"]:
                    record["url"] = url
                    record["source_ref"] = f"web:{_sha256(url)[:12]}"
            sources.extend(records)
        except Exception as exc:
            warnings.append(
                {
                    "status": "failed",
                    "skill": "web_browser_skill",
                    "url": url,
                    "message": str(exc),
                }
            )
    observed_source_count = sum(item.get("status") == "observed" for item in sources)
    minimum_before_search = max(
        0,
        min(max_seed_urls, int(internet.get("min_observed_sources_before_search", 4))),
    )
    search_only_for_gaps = bool(internet.get("search_only_when_source_gap", True))
    queries_to_run = [] if search_only_for_gaps and observed_source_count >= minimum_before_search else queries[:max_queries]
    for query in queries_to_run:
        if research_topic is None:
            if not any(
                warning.get("status") == "skill_unavailable"
                and warning.get("skill") == "web_browser_skill"
                for warning in warnings
            ):
                warnings.append({"status": "skill_unavailable", "skill": "web_browser_skill", "message": "Install mirrorneuron-web-browser-skill for public research."})
            break
        try:
            result = _call_optional(
                research_topic,
                query=query,
                config=browser_config,
                depth="standard",
                max_sources=max_sources,
                output_format="plain_text",
            )
            sources.extend(_normalize_browser_result(result, query, "web_browser_skill"))
            if isinstance(result, dict):
                for warning in result.get("warnings") or []:
                    warnings.append(
                        {
                            "status": "warning",
                            "skill": "web_browser_skill",
                            "query": query,
                            "message": str(warning),
                        }
                    )
        except Exception as exc:
            warnings.append({"status": "failed", "skill": "web_browser_skill", "query": query, "message": str(exc)})
    return sources, warnings


def _instantiate(cls: Any, values: dict[str, Any]) -> Any:
    if cls is None:
        return values
    try:
        params = inspect.signature(cls).parameters
        return cls(**{key: value for key, value in values.items() if key in params})
    except (TypeError, ValueError):
        return cls()


def deterministic_evidence(inputs: dict[str, Any], documents: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(str(item.get("text") or "") for item in documents)
    lowered = text.lower()
    price_values = [float(value.replace(",", "")) for value in re.findall(r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d{1,2})?)", text, flags=re.I)]
    budget = _number(inputs.get("budget"))
    flags: list[str] = []
    checks = {
        "return_or_cancellation_policy": any(term in lowered for term in ("return", "cancel", "refund")),
        "warranty_or_insurance": any(term in lowered for term in ("warranty", "insurance", "coverage")),
        "fees_and_taxes": any(term in lowered for term in ("fee", "tax", "surcharge", "hoa", "baggage")),
        "condition_or_inspection": any(term in lowered for term in ("inspection", "condition", "recall", "maintenance")),
    }
    for name, present in checks.items():
        if not present:
            flags.append(f"Missing evidence for {name.replace('_', ' ')}.")
    if budget is not None and price_values and min(price_values) > budget:
        flags.append("Observed price evidence exceeds the stated budget.")
    if any(item.get("status") == "blocked" for item in sources):
        flags.append("One or more public sources were blocked or access-limited.")
    source_refs = [item.get("source_ref") for item in documents + sources if item.get("source_ref")]
    return {
        "purchase_type": inputs.get("purchase_type"),
        "budget": budget,
        "observed_price_values": price_values[:20],
        "deterministic_checks": checks,
        "risk_flags": flags,
        "evidence_gaps": [name for name, present in checks.items() if not present],
        "document_count": len(documents),
        "public_source_count": len([item for item in sources if item.get("status") == "observed"]),
        "source_refs": source_refs,
    }


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(re.sub(r"[^0-9.-]", "", str(value)))
    except ValueError:
        return None


def deterministic_recommendation(evidence: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = len(evidence.get("evidence_gaps") or [])
    flags = len(evidence.get("risk_flags") or [])
    if not evidence.get("document_count") and not evidence.get("public_source_count"):
        label = "insufficient_evidence"
    elif flags >= 3 or gaps >= 3:
        label = "wait"
    elif flags >= 1 or gaps >= 1:
        label = "consider"
    else:
        label = "buy"
    confidence = "low" if gaps >= 3 else "medium" if gaps else "high"
    return {
        "label": label,
        "confidence": confidence,
        "rationale": "Recommendation is constrained by deterministic evidence checks and may change when missing evidence is supplied.",
        "risk_flags": list(evidence.get("risk_flags") or []),
        "evidence_gaps": list(evidence.get("evidence_gaps") or []),
        "public_source_status_counts": _status_counts(sources),
    }


def _normalize_intake_plan(response: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "normalized_goal": str(inputs.get("item_description") or "Study the requested purchase."),
        "category": str(inputs.get("purchase_type") or "custom"),
        "must_haves": list(inputs.get("priorities") or []),
        "deal_breakers": [],
        "decision_criteria": [
            "fit to the stated need",
            "total cost over the decision horizon",
            "quality, reliability, and safety",
            "terms, policy, and provider risk",
            "credible alternatives",
        ],
        "research_questions": [
            "What facts could materially change the decision?",
            "What is the total cost beyond the advertised price?",
            "What evidence is needed to verify quality, terms, and risk?",
        ],
        "public_query_topics": [],
        "unknowns": [],
        "technical_requirements": [],
        "commercial_requirements": [],
        "required_approvals": [],
    }
    if not isinstance(response, dict):
        return fallback
    normalized = dict(fallback)
    for key in ("normalized_goal", "category"):
        value = str(response.get(key) or "").strip()
        if value:
            normalized[key] = value[:500]
    for key in (
        "must_haves",
        "deal_breakers",
        "decision_criteria",
        "research_questions",
        "public_query_topics",
        "unknowns",
        "technical_requirements",
        "commercial_requirements",
        "required_approvals",
    ):
        values = response.get(key)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple, set)):
            cleaned = [str(item).strip()[:400] for item in values if str(item).strip()]
            normalized[key] = list(dict.fromkeys(cleaned))[:12]
    return normalized


def ask_llm_for_intake(llm: Any, inputs: dict[str, Any], documents: list[dict[str, Any]], knowledge: dict[str, Any]) -> dict[str, Any]:
    """Use the research model before retrieval so early workflow stages are model-guided."""
    fallback = _normalize_intake_plan({}, inputs)
    local_evidence = [
        {"source_ref": item.get("source_ref"), "name": item.get("name"), "text": _compact(item.get("text") or "", 2500)}
        for item in documents[:8]
    ]
    user = json.dumps(
        {
            "inputs": inputs,
            "local_evidence": local_evidence,
            "available_guidance": [item.get("name") for item in knowledge.get("files") or []],
            "output_contract": list(fallback.keys()),
        },
        sort_keys=True,
        default=str,
    )
    try:
        response = llm.generate_json(
            system_prompt=load_prompt("purchase-intake-task.md"),
            user_prompt=user,
            fallback=fallback,
        )
    except Exception:
        response = fallback
    return _normalize_intake_plan(response, inputs)


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def ask_llm_for_recommendation(llm: Any, inputs: dict[str, Any], evidence: dict[str, Any], rag: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    fallback = {"label": deterministic["label"], "confidence": deterministic["confidence"], "rationale": deterministic["rationale"]}
    prompt = load_prompt("purchase-review-task.md")
    system = load_prompt("recommendation-system.md")
    user = json.dumps({"inputs": inputs, "evidence": evidence, "rag_context": rag.get("context", ""), "deterministic_recommendation": deterministic}, sort_keys=True, default=str)
    try:
        response = llm.generate_json(system_prompt=system, user_prompt=f"{prompt}\n\n{user}", fallback=fallback)
    except Exception:
        response = fallback
    if not isinstance(response, dict):
        return fallback
    # Compatibility helper: models may explain a deterministic recommendation,
    # but they never own its label or confidence.
    return {
        "label": fallback["label"],
        "confidence": fallback["confidence"],
        "rationale": str(response.get("rationale") or fallback["rationale"])[:2000],
    }


__all__ = ['build_public_queries', 'sanitize_public_text', '_load_web_browser_skill', '_source_record', '_normalize_browser_result', 'research_public_sources', '_instantiate', 'deterministic_evidence', '_number', 'deterministic_recommendation', '_normalize_intake_plan', 'ask_llm_for_intake', '_status_counts', 'ask_llm_for_recommendation']
