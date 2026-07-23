"""Privacy-safe public research, deterministic comparison, and bounded LLM review."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from .common import RECOMMENDATIONS, _compact, _now, load_prompt


def build_public_queries(inputs: dict[str, Any], intake_plan: dict[str, Any] | None = None) -> list[str]:
    intake_plan = intake_plan if isinstance(intake_plan, dict) else {}
    constraint_parts = []
    for key, value in (inputs.get("constraints") or {}).items():
        safe_value = sanitize_public_text(value)
        safe_key = sanitize_public_text(key)
        if safe_key and safe_value:
            constraint_parts.append(f"{safe_key} {safe_value}")
    priority_parts = [sanitize_public_text(item) for item in inputs.get("priorities") or []]
    plan_topics = [sanitize_public_text(item) for item in intake_plan.get("public_query_topics") or []]
    base = " ".join(
        part for part in [
            inputs.get("purchase_type"),
            sanitize_public_text(inputs.get("item_description", "")),
            sanitize_public_text(inputs.get("location", "")),
            sanitize_public_text(inputs.get("route", "")),
            sanitize_public_text(inputs.get("travel_dates", "")),
            *priority_parts,
            *constraint_parts,
        ] if part
    ).strip()
    if not base:
        return []
    generic_topics = [
        "current price availability and comparable alternatives",
        "full total cost taxes fees recurring usage maintenance delivery and exit costs",
        "quality reliability safety compatibility warranty returns and support",
        "seller provider reputation policy eligibility privacy security and regulatory risks",
        "timing logistics constraints and what to verify before purchase",
    ]
    topics = {
        "property": ["market price taxes insurance inspection risks", "comparable listings fees ownership costs"],
        "rental_property": ["rent yield operating costs insurance tenant risks", "lease terms deposits maintenance fees"],
        "car": ["market price reliability ownership cost warranty recalls", "taxes registration insurance maintenance fees"],
        "airline_ticket": ["fare rules baggage seat fees cancellation change policy", "airport taxes schedule reliability alternatives"],
        "custom": ["category-specific price availability and alternatives", "category-specific quality policy compatibility and risks"],
    }
    selected_topics = list(dict.fromkeys([*plan_topics, *generic_topics, *topics.get(inputs.get("purchase_type"), topics["custom"])]))
    return [f"{base} {topic}" for topic in selected_topics if topic][:8]


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


def _load_w3m() -> tuple[Any, Any, Any]:
    try:
        from mn_w3m_browser_skill import W3mBrowserConfig, browse_url, research_topic
        return W3mBrowserConfig, browse_url, research_topic
    except Exception:
        return None, None, None


def _load_rendered_browser() -> tuple[Any, Any]:
    try:
        from mn_web_browser_skill import WebBrowserConfig, scrape_page
        return WebBrowserConfig, scrape_page
    except Exception:
        return None, None


def _source_record(*, url: str, title: str, snippet: str, status: str, skill: str, query: str, warning: str = "") -> dict[str, Any]:
    lowered = f"{title} {snippet} {warning}".lower()
    if any(marker in lowered for marker in ("captcha", "login required", "robots.txt", "access denied", "blocked")):
        status = "blocked"
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
        candidates = result.get("sources") or result.get("results") or result.get("items") or [result]
    elif isinstance(result, list):
        candidates = result
    else:
        candidates = [{"text": str(result or "")}] if result else []
    records = []
    for item in candidates:
        if isinstance(item, str):
            item = {"text": item}
        records.append(_source_record(
            url=str(item.get("url") or item.get("link") or ""),
            title=str(item.get("title") or item.get("name") or ""),
            snippet=str(item.get("snippet") or item.get("text") or item.get("content") or ""),
            status=str(item.get("status") or "observed"),
            skill=skill,
            query=query,
            warning=str(item.get("warning") or ""),
        ))
    return records


def research_public_sources(queries: list[str], config: dict[str, Any], *, quick_test: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if not internet.get("enabled", True):
        return [], [{"status": "disabled", "message": "Public research is disabled by configuration."}]
    if quick_test:
        return [], [{"status": "skipped_quick_test", "message": "Public research is skipped in fake/quick-test mode."}]
    sources: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    max_queries = int(internet.get("max_queries", 6))
    w3m_config_cls, browse_url, research_topic = _load_w3m()
    for query in queries[:max_queries]:
        if research_topic is None:
            warnings.append({"status": "skill_unavailable", "skill": "w3m_browser_skill", "message": "Install the w3m browser skill for public research."})
            break
        try:
            raw_config = {"timeout_seconds": internet.get("timeout_seconds", 20), "max_chars": internet.get("max_chars", 12000)}
            browser_config = _instantiate(w3m_config_cls, raw_config)
            result = _call_optional(research_topic, query=query, topic=query, config=browser_config, browser_config=browser_config, max_sources=int(internet.get("max_sources", 8)))
            sources.extend(_normalize_browser_result(result, query, "w3m_browser_skill"))
        except Exception as exc:
            warnings.append({"status": "failed", "skill": "w3m_browser_skill", "query": query, "message": str(exc)})
    if not sources and internet.get("rendered_browser", {}).get("enabled", True):
        rendered_cls, scrape_page = _load_rendered_browser()
        if scrape_page is None:
            warnings.append({"status": "skill_unavailable", "skill": "web_browser_skill", "message": "Rendered-browser fallback is unavailable."})
        else:
            for query in queries[:2]:
                url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query})
                try:
                    browser_config = _instantiate(rendered_cls, {"timeout_seconds": 30, "max_chars": 12000})
                    result = _call_optional(scrape_page, url=url, config=browser_config, browser_config=browser_config)
                    sources.extend(_normalize_browser_result(result, query, "web_browser_skill"))
                except Exception as exc:
                    warnings.append({"status": "failed", "skill": "web_browser_skill", "url": url, "message": str(exc)})
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
    }
    if not isinstance(response, dict):
        return fallback
    normalized = dict(fallback)
    for key in ("normalized_goal", "category"):
        value = str(response.get(key) or "").strip()
        if value:
            normalized[key] = value[:500]
    for key in ("must_haves", "deal_breakers", "decision_criteria", "research_questions", "public_query_topics", "unknowns"):
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
    label = str(response.get("label") or response.get("recommendation") or fallback["label"]).lower()
    if label not in RECOMMENDATIONS:
        label = fallback["label"]
    confidence = str(response.get("confidence") or fallback["confidence"]).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = fallback["confidence"]
    return {"label": label, "confidence": confidence, "rationale": str(response.get("rationale") or fallback["rationale"])[:2000]}


__all__ = ['build_public_queries', 'sanitize_public_text', '_load_w3m', '_load_rendered_browser', '_source_record', '_normalize_browser_result', 'research_public_sources', '_instantiate', 'deterministic_evidence', '_number', 'deterministic_recommendation', '_normalize_intake_plan', 'ask_llm_for_intake', '_status_counts', 'ask_llm_for_recommendation']
