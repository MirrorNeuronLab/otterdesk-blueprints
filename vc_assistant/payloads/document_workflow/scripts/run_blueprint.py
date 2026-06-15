#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from mn_blueprint_support import start_agent_beacon_thread
except Exception:  # pragma: no cover - optional runtime support
    def start_agent_beacon_thread(message: str | None = None) -> None:
        return None


BLUEPRINT_ID = "vc_assistant"
BLUEPRINT_NAME = "VC Assistant"
OUTPUT_TYPE = "vc_early_heuristic_analysis_reports"
RECOMMENDED_ACTION = "review_scores_sources_and_assumptions_before_making_any_investment_decision"
SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".json", ".csv"}
TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}
METHOD_IDS = [
    "berkus_method",
    "scorecard_bill_payne_method",
    "risk_factor_summation_method",
    "venture_capital_method",
    "first_chicago_method",
    "comparables_market_multiple_method",
    "cost_to_duplicate_method",
]
DEFAULT_RESEARCH_SOURCE_URLS = [
    "https://www.sba.gov/business-guide/plan-your-business/market-research-competitive-analysis",
    "https://www.sec.gov/education/smallbusiness",
    "https://www.bls.gov/",
]
DEFAULT_VERIFICATION_DOMAINS = [
    "crunchbase.com",
    "linkedin.com/company",
    "sec.gov",
    "company_website",
    "news_and_press",
]
DEFAULT_SOURCE_URL_TEMPLATES = [
    "https://www.crunchbase.com/organization/{company_slug}",
    "https://www.linkedin.com/company/{company_slug}",
    "https://www.sec.gov/edgar/search/",
]


W3mBrowserConfig = None
browse_url = None
build_search_url = None
research_topic = None
WebBrowserConfig = None
scrape_page = None


def _workspace_root() -> Path | None:
    value = os.environ.get("MN_WORKSPACE_ROOT")
    if value:
        return Path(value).expanduser()
    for parent in Path(__file__).resolve().parents:
        if (parent / "mn-skills").exists():
            return parent
    return None


def _add_repo_paths() -> None:
    workspace = _workspace_root()
    if not workspace:
        return
    for skill_name in ("w3m_browser_skill", "web_browser_skill"):
        candidate = workspace / "mn-skills" / skill_name / "src"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_add_repo_paths()


def _load_w3m_browser_skill() -> None:
    global W3mBrowserConfig, browse_url, build_search_url, research_topic
    if W3mBrowserConfig is not None and browse_url is not None and research_topic is not None:
        return
    try:
        from mn_w3m_browser_skill import W3mBrowserConfig as imported_config
        from mn_w3m_browser_skill import browse_url as imported_browse_url
        from mn_w3m_browser_skill import build_search_url as imported_build_search_url
        from mn_w3m_browser_skill import research_topic as imported_research_topic
    except Exception:
        return
    W3mBrowserConfig = imported_config
    browse_url = imported_browse_url
    build_search_url = imported_build_search_url
    research_topic = imported_research_topic


def _load_web_browser_skill() -> None:
    global WebBrowserConfig, scrape_page
    if WebBrowserConfig is not None and scrape_page is not None:
        return
    try:
        from mn_web_browser_skill import WebBrowserConfig as imported_config
        from mn_web_browser_skill import scrape_page as imported_scrape_page
    except Exception:
        return
    WebBrowserConfig = imported_config
    scrape_page = imported_scrape_page


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": payload}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_resolved_config(default_path: Path, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = read_json(default_path)
    env_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if env_path:
        resolved = deep_merge(resolved, read_json(Path(env_path)))
    env_json = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if env_json:
        decoded = json.loads(env_json)
        if isinstance(decoded, dict):
            resolved = deep_merge(resolved, decoded)
    if overlay:
        resolved = deep_merge(resolved, overlay)
    return resolved


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown-company"


def redactor(text: str) -> str:
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", text or "")
    value = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", value)
    value = re.sub(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED-PHONE]", value)
    return value


def safe_read_text(path: Path) -> tuple[str, list[str]]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return "", ["Non-text file recorded as evidence metadata only; OCR may be required."]
    try:
        return path.read_text(encoding="utf-8", errors="ignore"), []
    except Exception as exc:
        return "", [str(exc)]


def infer_company_name(path: Path, text: str, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    if len(relative.parts) > 1:
        return relative.parts[0].replace("_", " ").replace("-", " ").title()
    for pattern in (r"Company\s*[:\-]\s*([A-Za-z0-9 &.,-]+)", r"Startup\s*[:\-]\s*([A-Za-z0-9 &.,-]+)"):
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip(" .,-")[:80]
    return path.stem.replace("_", " ").replace("-", " ").title()


def scan_documents(folder: Path) -> dict[str, list[dict[str, Any]]]:
    records_by_company: dict[str, list[dict[str, Any]]] = {}
    if not folder.exists():
        return records_by_company
    for path in sorted(folder.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text, warnings = safe_read_text(path)
        redacted = redactor(text)
        company = infer_company_name(path, redacted, folder)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {
            "path": str(path),
            "filename": path.name,
            "company_name": company,
            "sha256": digest,
            "suffix": path.suffix.lower(),
            "text_preview": redacted[:1200],
            "character_count": len(redacted),
            "extraction_method": "embedded_text" if path.suffix.lower() in TEXT_SUFFIXES else "metadata_only",
            "ocr_required": path.suffix.lower() not in TEXT_SUFFIXES,
            "warnings": warnings,
        }
        records_by_company.setdefault(company, []).append(record)
    return records_by_company


def keyword_score(text: str, keywords: list[str], maximum: int = 100) -> int:
    haystack = text.lower()
    hits = sum(1 for keyword in keywords if keyword in haystack)
    return min(maximum, round((hits / max(1, len(keywords))) * maximum))


def evidence_status(score: int, minimum: int = 15) -> str:
    return "scored" if score >= minimum else "insufficient_evidence"


def money_values(text: str) -> list[float]:
    values = []
    for match in re.finditer(r"\$?\s?(\d+(?:\.\d+)?)\s?(m|million|k|thousand)?", text, flags=re.I):
        raw = float(match.group(1))
        suffix = (match.group(2) or "").lower()
        if suffix in {"m", "million"}:
            raw *= 1_000_000
        elif suffix in {"k", "thousand"}:
            raw *= 1_000
        values.append(raw)
    return values[:20]


def score_company(company: str, records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(str(record.get("text_preview") or "") for record in records)
    values = money_values(text)
    traction_score = keyword_score(text, ["revenue", "customer", "pilot", "contract", "growth", "retention", "sales"])
    team_score = keyword_score(text, ["founder", "team", "advisor", "operator", "engineer", "domain expert"])
    market_score = keyword_score(text, ["tam", "sam", "market", "industry", "competition", "segment", "buyer"])
    product_score = keyword_score(text, ["prototype", "mvp", "product", "platform", "demo", "patent", "technology"])
    relationship_score = keyword_score(text, ["partner", "channel", "strategic", "distribution", "enterprise", "supplier"])
    risk_score = keyword_score(text, ["risk", "regulatory", "churn", "burn", "competition", "dependency", "lawsuit"])
    cost_score = keyword_score(text, ["built", "patent", "r&d", "dataset", "hardware", "model", "infrastructure"])

    berkus_buckets = {
        "sound_idea": market_score,
        "prototype": product_score,
        "quality_management_team": team_score,
        "strategic_relationships": relationship_score,
        "product_rollout_or_sales": traction_score,
    }
    scorecard_weights = {
        "team": 0.30,
        "market": 0.25,
        "product": 0.15,
        "traction": 0.15,
        "competition": 0.10,
        "financing_need": 0.05,
    }
    scorecard_factors = {
        "team": team_score,
        "market": market_score,
        "product": product_score,
        "traction": traction_score,
        "competition": max(0, 100 - risk_score),
        "financing_need": 60 if values else 25,
    }
    risk_factors = [
        "management", "stage", "legislation", "manufacturing", "sales", "funding",
        "competition", "technology", "litigation", "international", "reputation", "exit",
    ]
    risk_adjustments = {
        factor: {"adjustment": round((keyword_score(text, [factor]) - 50) / 25, 2), "status": "scored" if factor in text.lower() else "insufficient_evidence"}
        for factor in risk_factors
    }
    assumed_exit_value = max(values) * 8 if values else None
    vc_method_status = "scored" if assumed_exit_value else "insufficient_evidence"
    first_chicago_status = "scored" if traction_score >= 15 and values else "insufficient_evidence"
    comparable_status = "scored" if sources else "insufficient_evidence"
    cost_status = evidence_status(cost_score)

    methods = {
        "berkus_method": {
            "memory_hook": "5 buckets",
            "status": "scored" if any(berkus_buckets.values()) else "insufficient_evidence",
            "score": round(sum(berkus_buckets.values()) / len(berkus_buckets), 2),
            "buckets": berkus_buckets,
            "assumptions": ["Scores are heuristic 0-100 evidence-strength indicators, not valuation advice."],
        },
        "scorecard_bill_payne_method": {
            "memory_hook": "Compare to the average startup",
            "status": "scored" if any(scorecard_factors.values()) else "insufficient_evidence",
            "score": round(sum(scorecard_factors[key] * weight for key, weight in scorecard_weights.items()), 2),
            "weights": scorecard_weights,
            "factors": scorecard_factors,
        },
        "risk_factor_summation_method": {
            "memory_hook": "12-risk checklist",
            "status": "scored" if risk_score else "insufficient_evidence",
            "score": round(max(0, 100 - risk_score), 2),
            "risk_adjustments": risk_adjustments,
        },
        "venture_capital_method": {
            "memory_hook": "Work backward from exit",
            "status": vc_method_status,
            "score": round(min(100, traction_score * 0.6 + market_score * 0.4), 2) if assumed_exit_value else None,
            "assumed_exit_value": assumed_exit_value,
            "required_return_multiple": 10,
            "notes": "Uses the largest extracted monetary figure as a rough proxy only when available.",
        },
        "first_chicago_method": {
            "memory_hook": "Bear/base/bull cases",
            "status": first_chicago_status,
            "score": round((traction_score + market_score + product_score) / 3, 2) if first_chicago_status == "scored" else None,
            "cases": {
                "bear": {"probability": 0.35, "score": max(0, traction_score - 25)},
                "base": {"probability": 0.45, "score": round((traction_score + market_score) / 2, 2)},
                "bull": {"probability": 0.20, "score": min(100, max(traction_score, market_score) + 20)},
            },
        },
        "comparables_market_multiple_method": {
            "memory_hook": "What are similar companies worth?",
            "status": comparable_status,
            "score": round((market_score + traction_score) / 2, 2) if sources else None,
            "source_count": len(sources),
            "notes": "Comparable evidence is limited to public research snippets captured during the run.",
        },
        "cost_to_duplicate_method": {
            "memory_hook": "What would it cost to rebuild?",
            "status": cost_status,
            "score": cost_score if cost_status == "scored" else None,
            "evidence_terms": ["built", "patent", "r&d", "dataset", "hardware", "model", "infrastructure"],
        },
    }
    scored = [item["score"] for item in methods.values() if isinstance(item.get("score"), (int, float))]
    return {
        "company_name": company,
        "company_slug": slugify(company),
        "composite_score": round(sum(scored) / len(scored), 2) if scored else None,
        "method_count": len(methods),
        "methods": methods,
        "evidence_summary": {
            "document_count": len(records),
            "source_count": len(sources),
            "missing_methods": [method_id for method_id, method in methods.items() if method["status"] == "insufficient_evidence"],
        },
        "decision_policy": "report_only_user_decides",
    }


def _research_observer(run_dir: Path | None):
    def observe(event_type: str, payload: dict[str, Any]) -> None:
        if run_dir is None:
            return
        append_event(run_dir, event_type, payload)

    return observe


def _configured_research(company: str, internet: dict[str, Any]) -> dict[str, Any]:
    company_slug = slugify(company)
    query_terms = [
        f"{company} startup funding founders Crunchbase",
        f"{company} startup competitors market traction",
        f"{company} company website press customers product",
    ]
    templates = list(internet.get("source_url_templates") or DEFAULT_SOURCE_URL_TEMPLATES)
    target_urls = [template.format(company=company, company_slug=company_slug) for template in templates]
    return {
        "company": company,
        "company_slug": company_slug,
        "queries": query_terms[: int(internet.get("max_queries") or 3)],
        "target_urls": target_urls,
        "verification_domains": list(internet.get("verification_domains") or DEFAULT_VERIFICATION_DOMAINS),
        "verification_fields": list(
            internet.get("verification_fields")
            or [
                "company_profile",
                "founders",
                "funding",
                "category",
                "competitors",
                "traction_claims",
                "source_conflicts",
            ]
        ),
        "privacy_policy": "Queries use company names and public descriptors only; confidential document excerpts are blocked.",
    }


def _source_record(
    *,
    company: str,
    query: str,
    url: str,
    title: str,
    snippet: str,
    status: str,
    skill: str,
    verification_target: str,
    warning: str = "",
) -> dict[str, Any]:
    return {
        "company": company,
        "query": query,
        "url": url,
        "title": title or url.split("//", 1)[-1].split("/", 1)[0],
        "snippet": snippet[:1000],
        "status": status,
        "skill": skill,
        "verification_target": verification_target,
        "warning": warning,
        "retrieved_at": utc_now_iso(),
    }


def _append_w3m_research(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
) -> None:
    _load_w3m_browser_skill()
    query = plan["queries"][0]
    max_sources = int(internet.get("max_sources_per_company") or 3)
    if W3mBrowserConfig is None or research_topic is None or browse_url is None:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url="w3m_browser_skill",
                title="w3m browser skill unavailable",
                snippet="Install mirrorneuron-w3m-browser-skill and w3m in the worker image to enable lightweight public research.",
                status="skill_unavailable",
                skill="w3m_browser_skill",
                verification_target="online_research_setup",
                warning="mn_w3m_browser_skill import failed",
            )
        )
        return
    browser_config = W3mBrowserConfig(
        timeout_seconds=int(internet.get("timeout_seconds") or 12),
        max_chars=int(internet.get("max_chars") or 6000),
        search_url_template=str(internet.get("search_url_template") or "https://duckduckgo.com/html/?q={query}"),
    )
    observer = _research_observer(run_dir)
    try:
        result = research_topic(query, browser_config, max_sources=max_sources, observer=observer)
    except Exception as exc:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url="w3m_browser_skill",
                title="w3m research failed",
                snippet=str(exc),
                status="failed",
                skill="w3m_browser_skill",
                verification_target="search_results",
                warning=str(exc),
            )
        )
        return
    for source in result.get("sources") or []:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(source.get("url") or ""),
                title=str(source.get("title") or ""),
                snippet=str(source.get("snippet") or source.get("text") or ""),
                status=str(source.get("status") or "ok"),
                skill="w3m_browser_skill",
                verification_target="search_result_or_public_source",
            )
        )
    for warning in result.get("warnings") or []:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(result.get("search_url") or ""),
                title="w3m research warning",
                snippet=str(warning),
                status="warning",
                skill="w3m_browser_skill",
                verification_target="search_results",
                warning=str(warning),
            )
        )


def _append_target_url_research(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
) -> None:
    _load_w3m_browser_skill()
    if W3mBrowserConfig is None or browse_url is None:
        return
    browser_config = W3mBrowserConfig(
        timeout_seconds=int(internet.get("timeout_seconds") or 12),
        max_chars=int(internet.get("max_chars") or 6000),
    )
    observer = _research_observer(run_dir)
    for url in plan["target_urls"][: int(internet.get("max_target_urls_per_company") or 2)]:
        target = "crunchbase" if "crunchbase.com" in url else "public_profile"
        try:
            result = browse_url(url, browser_config, observer=observer)
        except Exception as exc:
            result = {"status": "failed", "url": url, "title": "", "snippet": "", "error": str(exc)}
        sources.append(
            _source_record(
                company=company,
                query=plan["queries"][0],
                url=str(result.get("url") or url),
                title=str(result.get("title") or ""),
                snippet=str(result.get("snippet") or result.get("text") or result.get("error") or ""),
                status=str(result.get("status") or "failed"),
                skill="w3m_browser_skill",
                verification_target=target,
                warning=str(result.get("error") or ""),
            )
        )


def _append_rendered_browser_research(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
) -> None:
    rendered = internet.get("rendered_browser") if isinstance(internet.get("rendered_browser"), dict) else {}
    if rendered.get("enabled") is not True:
        return
    _load_web_browser_skill()
    if WebBrowserConfig is None or scrape_page is None:
        sources.append(
            _source_record(
                company=company,
                query=plan["queries"][0],
                url="web_browser_skill",
                title="rendered browser skill unavailable",
                snippet="Install mirrorneuron-web-browser-skill with Playwright to inspect JavaScript-rendered startup profiles.",
                status="skill_unavailable",
                skill="web_browser_skill",
                verification_target="rendered_page_setup",
                warning="mn_web_browser_skill import failed",
            )
        )
        return
    browser_config = WebBrowserConfig(
        timeout_seconds=int(rendered.get("timeout_seconds") or 20),
        max_chars=int(rendered.get("max_chars") or 12000),
        respect_robots=bool(rendered.get("respect_robots", True)),
        per_host_delay_seconds=float(rendered.get("per_host_delay_seconds") or 1.0),
    )
    for url in plan["target_urls"][: int(rendered.get("max_pages_per_company") or 1)]:
        try:
            result = scrape_page(url, browser_config)
        except Exception as exc:
            result = {"status": "failed", "url": url, "title": "", "text": "", "error": str(exc), "warnings": []}
        sources.append(
            _source_record(
                company=company,
                query=plan["queries"][0],
                url=str(result.get("final_url") or result.get("url") or url),
                title=str(result.get("title") or ""),
                snippet=str(result.get("text") or result.get("error") or ""),
                status=str(result.get("status") or "failed"),
                skill="web_browser_skill",
                verification_target="rendered_public_profile",
                warning="; ".join(str(item) for item in (result.get("warnings") or [])) or str(result.get("error") or ""),
            )
        )


def research_company(company: str, config: dict[str, Any], run_dir: Path | None = None) -> list[dict[str, Any]]:
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if internet.get("enabled") is False:
        return []
    plan = _configured_research(company, internet)
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
    _append_w3m_research(sources, company=company, plan=plan, internet=internet, run_dir=run_dir)
    _append_target_url_research(sources, company=company, plan=plan, internet=internet, run_dir=run_dir)
    _append_rendered_browser_research(sources, company=company, plan=plan, internet=internet)
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


def render_markdown(analysis: dict[str, Any], sources: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    lines = [
        f"# {analysis['company_name']} VC Heuristic Report",
        "",
        "This is a score-only early screening report. It does not issue an investment decision.",
        "",
        f"Composite score: {analysis['composite_score']}",
        "",
        "## Method Scores",
    ]
    for method_id in METHOD_IDS:
        method = analysis["methods"][method_id]
        lines += [
            f"### {method_id.replace('_', ' ').title()}",
            f"- Status: {method['status']}",
            f"- Score: {method.get('score') if method.get('score') is not None else 'insufficient_evidence'}",
            f"- Memory hook: {method['memory_hook']}",
        ]
    lines += ["", "## Evidence", f"- Local documents: {len(evidence)}", f"- Public sources: {len(sources)}", ""]
    for item in evidence[:8]:
        lines.append(f"- {item['filename']}: {item.get('extraction_method')} ({item.get('sha256', '')[:12]})")
    lines += ["", "## Public Sources"]
    for source in sources:
        lines.append(f"- {source['title']}: {source['url']}")
    lines += ["", "## User Decision Boundary", "Use the scores, assumptions, and source refs to decide what to review next."]
    return "\n".join(lines) + "\n"


def write_company_outputs(output_folder: Path, analyses: list[dict[str, Any]], company_records: dict[str, list[dict[str, Any]]], company_sources: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    output_files = []
    for analysis in analyses:
        slug = analysis["company_slug"]
        company_dir = output_folder / slug
        evidence = company_records[analysis["company_name"]]
        sources = company_sources[analysis["company_name"]]
        write_json(company_dir / "analysis.json", analysis)
        write_json(company_dir / "sources.json", sources)
        write_json(company_dir / "evidence.json", evidence)
        markdown = render_markdown(analysis, sources, evidence)
        (company_dir / "analysis.md").write_text(markdown, encoding="utf-8")
        for name in ("analysis.json", "analysis.md", "sources.json", "evidence.json"):
            output_files.append({"kind": name.rsplit(".", 1)[0], "path": str(company_dir / name), "company": analysis["company_name"]})
    index = {
        "blueprint_id": BLUEPRINT_ID,
        "generated_at": utc_now_iso(),
        "report_only": True,
        "companies": [
            {
                "company_name": analysis["company_name"],
                "company_slug": analysis["company_slug"],
                "composite_score": analysis["composite_score"],
                "missing_methods": analysis["evidence_summary"]["missing_methods"],
            }
            for analysis in analyses
        ],
    }
    write_json(output_folder / "company_index.json", index)
    index_lines = ["# VC Heuristic Company Index", "", "Report-only score summaries. The user decides what to do next.", ""]
    for item in index["companies"]:
        index_lines.append(f"- {item['company_name']}: composite score {item['composite_score']}")
    (output_folder / "company_index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    output_files.extend([
        {"kind": "company_index_json", "path": str(output_folder / "company_index.json")},
        {"kind": "company_index_markdown", "path": str(output_folder / "company_index.md")},
    ])
    return output_files


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    del llm_client
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    blueprint_dir = Path(__file__).resolve().parents[3]
    resolved_config = load_resolved_config(blueprint_dir / "config" / "default.json", config)
    payload = dict((resolved_config.get("inputs") or {}).get("payload") or {})
    if inputs:
        payload.update(inputs)
    run_id = run_id or payload.get("run_id") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    output_folder = Path(payload.get("output_folder") or (resolved_config.get("outputs") or {}).get("folder_path") or f"~/Download/{BLUEPRINT_ID}").expanduser()
    runs_root_path = Path(runs_root).expanduser() if runs_root else output_folder / "runs"
    run_dir = runs_root_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    document_folder = Path(payload.get("document_folder") or "").expanduser() if payload.get("document_folder") else blueprint_dir / "examples" / "sample_inputs"
    monitoring = dict(payload.get("monitoring") or {})
    max_cycles = int(monitoring.get("max_cycles") or 1)

    write_json(run_dir / "config.json", resolved_config)
    write_json(run_dir / "inputs.json", {"payload": payload, "document_folder": str(document_folder)})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()})
    append_event(run_dir, "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "watch_cycle_started", {"cycle": 1, "max_cycles": max_cycles})
    append_event(run_dir, "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})

    company_records = scan_documents(document_folder)
    if not company_records:
        company_records = {"Sample Startup": []}
    company_sources = {company: research_company(company, resolved_config, run_dir) for company in company_records}
    analyses = [score_company(company, records, company_sources[company]) for company, records in sorted(company_records.items())]
    output_files = write_company_outputs(output_folder, analyses, company_records, company_sources)
    append_event(run_dir, "startup_folder_watcher_completed", {"company_count": len(company_records)})
    append_event(run_dir, "startup_document_reader_completed", {"document_count": sum(len(records) for records in company_records.values())})
    append_event(run_dir, "public_market_researcher_completed", {"company_count": len(company_sources)})
    append_event(run_dir, "vc_heuristic_scorer_completed", {"method_count": len(METHOD_IDS)})
    append_event(run_dir, "vc_report_writer_completed", {"output_folder": str(output_folder)})
    append_event(run_dir, "watch_cycle_completed", {"cycle": 1, "companies": len(company_records)})

    final_artifact = {
        "type": OUTPUT_TYPE,
        "executive_summary": f"{BLUEPRINT_NAME} prepared score-only VC heuristic reports for {len(analyses)} startup companies.",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": 0.74 if any(item["composite_score"] is not None for item in analyses) else 0.35,
        "evidence": [record for records in company_records.values() for record in records[:5]],
        "next_steps": [
            "Review each company subfolder before deciding what to diligence next.",
            "Check insufficient_evidence method sections and add source documents where needed.",
            "Use public source refs only as context; verify material claims independently.",
        ],
        "source_refs": ["inputs.json", "events.jsonl", "result.json", "company_index.json"],
        "research_summary": {"company_count": len(company_sources), "privacy_policy": "no confidential excerpts in public research queries"},
        "research_sources": [source for sources in company_sources.values() for source in sources],
        "research_warnings": [],
        "report_only": True,
        "company_reports": analyses,
        "method_ids": METHOD_IDS,
        "monitor_state": {"mode": "folder_monitoring", "cycles_completed": 1, "max_cycles": max_cycles},
        "output_files": output_files,
        "llm_usage": {"provider": "none", "model": "deterministic_heuristics", "calls": 0, "fallback_calls": 0},
    }
    result = {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "final_artifact": final_artifact}

    append_event(run_dir, "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(run_dir, "human_input_requested", {"mode": "approval_required", "reason": "Reports contain heuristic investment-analysis scores for human review only."})
    append_event(run_dir, "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "final_artifact.json", final_artifact)
    write_json(run_dir / "watch_state.json", final_artifact["monitor_state"])
    append_event(run_dir, "artifact_written", {"path": "result.json"})
    append_event(run_dir, "artifact_written", {"path": "final_artifact.json"})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=BLUEPRINT_NAME)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    inputs: dict[str, Any] = {}
    if args.input_folder:
        inputs["document_folder"] = args.input_folder
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    result = run_blueprint(inputs=inputs, runs_root=args.runs_root or None, run_id=args.run_id or None)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"], "final_artifact": result["final_artifact"]}, indent=2))


if __name__ == "__main__":
    main()
