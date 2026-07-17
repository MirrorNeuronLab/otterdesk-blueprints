"""Concrete public browser and HTTP research adapters."""

from __future__ import annotations

from .common import *
from .research_core import (
    _budget_exhausted_source,
    _mock_public_source,
    _research_observer,
    _source_record,
)
from .runtime_tools import append_observation_record, observed_operation, stable_text_hash

def _load_web_browser_skill() -> None:
    global WebBrowserConfig, browse, research_topic
    if WebBrowserConfig is not None and browse is not None and research_topic is not None:
        return
    with SKILL_LOAD_LOCK:
        if WebBrowserConfig is not None and browse is not None and research_topic is not None:
            return
        try:
            from mn_web_browser_skill import WebBrowserConfig as imported_config
            from mn_web_browser_skill import browse as imported_browse
            from mn_web_browser_skill import research_topic as imported_research_topic
        except Exception:
            return
        WebBrowserConfig = imported_config
        browse = imported_browse
        research_topic = imported_research_topic

def _browser_config(settings: dict[str, Any]) -> Any:
    return WebBrowserConfig(
        timeout_seconds=int(settings.get("timeout_seconds") or 20),
        total_timeout_seconds=int(settings.get("total_timeout_seconds") or 60),
        max_chars=int(settings.get("max_chars") or 12000),
        output_format="plain_text",
        respect_robots=bool(settings.get("respect_robots", True)),
        per_host_delay_seconds=float(settings.get("per_host_delay_seconds") or 1.0),
    )


def _append_browser_research(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    verification_target: str = "search_result_or_public_source",
    action_budget: ActionBudget | None = None,
) -> None:
    source_count_start = len(sources)
    tool_status = "completed"
    tool_error = ""
    op = observed_operation(
        run_dir,
        phase="public_tool_call",
        operation="web_browser_skill.research_topic",
        tool="web_browser_skill.research_topic",
        company=company,
        verification_target=verification_target,
        query_hash=stable_text_hash((plan.get("queries") or [""])[0]),
        query_chars=len(str((plan.get("queries") or [""])[0])),
    ).__enter__()
    try:
        _append_browser_research_unobserved(
            sources,
            company=company,
            plan=plan,
            internet=internet,
            run_dir=run_dir,
            verification_target=verification_target,
            action_budget=action_budget,
        )
        new_sources = sources[source_count_start:]
        if any(source.get("mocked") for source in new_sources):
            tool_status = "mocked"
        failed_statuses = {str(source.get("status") or "") for source in new_sources if str(source.get("status") or "") in WARNING_SOURCE_STATUSES}
        if failed_statuses:
            tool_status = sorted(failed_statuses)[0]
        if new_sources:
            tool_error = "; ".join(str(source.get("warning") or "") for source in new_sources if source.get("warning"))[:500]
    except Exception as exc:
        tool_status = "failed"
        tool_error = str(exc)
        raise
    finally:
        op.close(
            "completed" if tool_status in {"completed", "ok", "", "mocked"} else "failed",
            tool_status=tool_status,
            source_count=len(sources) - source_count_start,
            error=tool_error,
            mocked=tool_status == "mocked",
        )

def _append_browser_research_unobserved(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    verification_target: str = "search_result_or_public_source",
    action_budget: ActionBudget | None = None,
) -> None:
    if fake_skills_mode_enabled():
        query = str((plan.get("queries") or [company])[0])
        sources.append(
            _mock_public_source(
                company=company,
                query=query,
                skill="web_browser_skill.research_topic",
                verification_target=verification_target,
            )
        )
        append_observation_record(
            run_dir,
            "skill_mock_used",
            {
                "phase": "public_tool_call",
                "operation": "web_browser_skill.research_topic",
                "tool": "web_browser_skill.research_topic",
                "status": "mocked",
                "company": company,
                "mocked": True,
                "source_count": 1,
            },
        )
        return
    _load_web_browser_skill()
    query = plan["queries"][0]
    max_sources = int(internet.get("max_sources_per_company") or 3)
    if WebBrowserConfig is None or research_topic is None or browse is None:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url="web_browser_skill",
                title="web browser skill unavailable",
                snippet="Install mirrorneuron-web-browser-skill and its local browser prerequisites to enable public research.",
                status="skill_unavailable",
                skill="web_browser_skill",
                verification_target=verification_target,
                warning="mn_web_browser_skill import failed",
            )
        )
        return
    browser_config = _browser_config(internet)
    observer = _research_observer(run_dir)
    action = action_budget.start(
        action_type="browser_search",
        stage=verification_target,
        company=company,
        tool="web_browser_skill.research_topic",
        metadata={"query": query, "max_sources": max_sources, "depth": "standard"},
    ) if action_budget else None
    if action_budget and action is None:
        sources.append(_budget_exhausted_source(company, query, "web_browser_skill", verification_target, "browser_search"))
        return
    try:
        result = research_topic(
            query,
            browser_config,
            depth="standard",
            max_sources=max_sources,
            observer=observer,
            output_format="plain_text",
        )
    except Exception as exc:
        if action_budget:
            action_budget.complete(action, "failed", {"error": str(exc)})
        sources.append(
            _source_record(
                company=company,
                query=query,
                url="web_browser_skill",
                title="web research failed",
                snippet=str(exc),
                status="failed",
                skill="web_browser_skill",
                verification_target=verification_target,
                warning=str(exc),
            )
        )
        return
    if action_budget:
        action_budget.complete(action, "completed", {"source_count": len(result.get("sources") or [])})
    for source in result.get("sources") or []:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(source.get("final_url") or source.get("url") or ""),
                title=str(source.get("title") or ""),
                snippet=str(source.get("snippet") or source.get("text") or ""),
                status=str(source.get("status") or "ok"),
                skill="web_browser_skill",
                verification_target=verification_target,
            )
        )
    for warning in result.get("warnings") or []:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(result.get("search_url") or ""),
                title="web research warning",
                snippet=str(warning),
                status="warning",
                skill="web_browser_skill",
                verification_target=verification_target,
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
    action_budget: ActionBudget | None = None,
) -> None:
    source_count_start = len(sources)
    tool_status = "completed"
    tool_error = ""
    target_urls = plan.get("target_urls") or []
    op = observed_operation(
        run_dir,
        phase="public_tool_call",
        operation="web_browser_skill.browse",
        tool="web_browser_skill.browse",
        company=company,
        url_count=len(target_urls),
        url_hash=stable_text_hash("\n".join(str(url) for url in target_urls[:10])),
    ).__enter__()
    try:
        _append_target_url_research_unobserved(
            sources,
            company=company,
            plan=plan,
            internet=internet,
            run_dir=run_dir,
            action_budget=action_budget,
        )
        new_sources = sources[source_count_start:]
        if any(source.get("mocked") for source in new_sources):
            tool_status = "mocked"
        failed_statuses = {str(source.get("status") or "") for source in new_sources if str(source.get("status") or "") in WARNING_SOURCE_STATUSES}
        if failed_statuses:
            tool_status = sorted(failed_statuses)[0]
        if new_sources:
            tool_error = "; ".join(str(source.get("warning") or "") for source in new_sources if source.get("warning"))[:500]
    except Exception as exc:
        tool_status = "failed"
        tool_error = str(exc)
        raise
    finally:
        op.close(
            "completed" if tool_status in {"completed", "ok", "", "mocked"} else "failed",
            tool_status=tool_status,
            source_count=len(sources) - source_count_start,
            error=tool_error,
            mocked=tool_status == "mocked",
        )

def _append_target_url_research_unobserved(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    action_budget: ActionBudget | None = None,
) -> None:
    if fake_skills_mode_enabled():
        query = str((plan.get("queries") or [company])[0])
        urls = plan.get("target_urls") or [""]
        for url in urls[: int(internet.get("max_target_urls_per_company") or 2)]:
            sources.append(
                _mock_public_source(
                    company=company,
                    query=query,
                    url=str(url or ""),
                    skill="web_browser_skill.browse",
                    verification_target="public_profile",
                )
            )
        append_observation_record(
            run_dir,
            "skill_mock_used",
            {
                "phase": "public_tool_call",
                "operation": "web_browser_skill.browse",
                "tool": "web_browser_skill.browse",
                "status": "mocked",
                "company": company,
                "mocked": True,
                "source_count": len(urls[: int(internet.get("max_target_urls_per_company") or 2)]),
            },
        )
        return
    _load_web_browser_skill()
    if WebBrowserConfig is None or browse is None:
        for url in plan["target_urls"][: int(internet.get("max_target_urls_per_company") or 2)]:
            sources.append(
                _source_record(
                    company=company,
                    query=plan["queries"][0],
                    url=url or "web_browser_skill",
                    title="web browser skill unavailable",
                    snippet="Install mirrorneuron-web-browser-skill and its local browser prerequisites to enable direct public-page research.",
                    status="skill_unavailable",
                    skill="web_browser_skill",
                    verification_target="public_profile",
                    warning="mn_web_browser_skill import failed",
                )
            )
        return
    browser_config = _browser_config(internet)
    observer = _research_observer(run_dir)
    for url in plan["target_urls"][: int(internet.get("max_target_urls_per_company") or 2)]:
        target = "crunchbase" if "crunchbase.com" in url else "public_profile"
        action = action_budget.start(
            action_type="browser_page",
            stage=target,
            company=company,
            tool="web_browser_skill.browse",
            metadata={"url": url, "depth": "standard"},
        ) if action_budget else None
        if action_budget and action is None:
            sources.append(_budget_exhausted_source(company, plan["queries"][0], "web_browser_skill", target, "browser_page"))
            continue
        try:
            result = browse(
                url,
                browser_config,
                depth="standard",
                observer=observer,
                output_format="plain_text",
            )
        except Exception as exc:
            result = {"status": "failed", "url": url, "title": "", "snippet": "", "error": str(exc)}
            if action_budget:
                action_budget.complete(action, "failed", {"url": url, "error": str(exc)})
        else:
            if action_budget:
                action_budget.complete(action, str(result.get("status") or "completed"), {"url": str(result.get("url") or url)})
        sources.append(
            _source_record(
                company=company,
                query=plan["queries"][0],
                url=str(result.get("final_url") or result.get("url") or url),
                title=str(result.get("title") or ""),
                snippet=str(result.get("snippet") or result.get("text") or result.get("error") or ""),
                status=str(result.get("status") or "failed"),
                skill="web_browser_skill",
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
    run_dir: Path | None = None,
    action_budget: ActionBudget | None = None,
) -> None:
    source_count_start = len(sources)
    tool_status = "completed"
    tool_error = ""
    target_urls = plan.get("target_urls") or []
    op = observed_operation(
        run_dir,
        phase="public_tool_call",
        operation="web_browser_skill.browse.deep",
        tool="web_browser_skill.browse",
        company=company,
        url_count=len(target_urls),
        url_hash=stable_text_hash("\n".join(str(url) for url in target_urls[:10])),
    ).__enter__()
    try:
        _append_rendered_browser_research_unobserved(
            sources,
            company=company,
            plan=plan,
            internet=internet,
            action_budget=action_budget,
        )
        new_sources = sources[source_count_start:]
        if any(source.get("mocked") for source in new_sources):
            tool_status = "mocked"
        failed_statuses = {str(source.get("status") or "") for source in new_sources if str(source.get("status") or "") in WARNING_SOURCE_STATUSES}
        if failed_statuses:
            tool_status = sorted(failed_statuses)[0]
        if new_sources:
            tool_error = "; ".join(str(source.get("warning") or "") for source in new_sources if source.get("warning"))[:500]
    except Exception as exc:
        tool_status = "failed"
        tool_error = str(exc)
        raise
    finally:
        op.close(
            "completed" if tool_status in {"completed", "ok", "", "mocked"} else "failed",
            tool_status=tool_status,
            source_count=len(sources) - source_count_start,
            error=tool_error,
            mocked=tool_status == "mocked",
        )

def _append_rendered_browser_research_unobserved(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    action_budget: ActionBudget | None = None,
) -> None:
    rendered = internet.get("rendered_browser") if isinstance(internet.get("rendered_browser"), dict) else {}
    if rendered.get("enabled") is not True:
        return
    if fake_skills_mode_enabled():
        query = str((plan.get("queries") or [company])[0])
        for url in (plan.get("target_urls") or [""])[: int(rendered.get("max_pages_per_company") or 1)]:
            sources.append(
                _mock_public_source(
                    company=company,
                    query=query,
                    url=str(url or ""),
                    skill="web_browser_skill.browse",
                    verification_target="rendered_public_profile",
                )
            )
        return
    _load_web_browser_skill()
    if WebBrowserConfig is None or browse is None:
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
    browser_config = _browser_config(rendered)
    for url in plan["target_urls"][: int(rendered.get("max_pages_per_company") or 1)]:
        action = action_budget.start(
            action_type="rendered_browser_page",
            stage="rendered_page_researcher",
            company=company,
            tool="web_browser_skill.browse",
            metadata={"url": url, "depth": "deep"},
        ) if action_budget else None
        if action_budget and action is None:
            sources.append(_budget_exhausted_source(company, plan["queries"][0], "web_browser_skill", "rendered_public_profile", "rendered_browser_page"))
            continue
        try:
            result = browse(
                url,
                browser_config,
                depth="deep",
                output_format="plain_text",
            )
        except Exception as exc:
            result = {"status": "failed", "url": url, "title": "", "text": "", "error": str(exc), "warnings": []}
            if action_budget:
                action_budget.complete(action, "failed", {"url": url, "error": str(exc)})
        else:
            if action_budget:
                action_budget.complete(action, str(result.get("status") or "completed"), {"url": str(result.get("final_url") or result.get("url") or url)})
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
