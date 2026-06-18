#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
WORKFLOW_STEP_IDS = [
    "startup_folder_watcher",
    "company_packet_grouper",
    "document_evidence_extractor",
    "claim_normalizer",
    "research_planner",
    "company_identity_researcher",
    "funding_researcher",
    "market_comp_researcher",
    "traction_verifier",
    "rendered_page_researcher",
    "research_reconciler",
    "berkus_scorer",
    "scorecard_bill_payne_scorer",
    "risk_factor_summation_scorer",
    "venture_capital_method_scorer",
    "first_chicago_scorer",
    "comparables_market_multiple_scorer",
    "cost_to_duplicate_scorer",
    "score_consistency_auditor",
    "company_report_writer",
    "batch_index_writer",
]
RESEARCH_STAGE_IDS = [
    "company_identity_researcher",
    "funding_researcher",
    "market_comp_researcher",
    "traction_verifier",
    "rendered_page_researcher",
]
SCORER_STAGE_BY_METHOD = {
    "berkus_method": "berkus_scorer",
    "scorecard_bill_payne_method": "scorecard_bill_payne_scorer",
    "risk_factor_summation_method": "risk_factor_summation_scorer",
    "venture_capital_method": "venture_capital_method_scorer",
    "first_chicago_method": "first_chicago_scorer",
    "comparables_market_multiple_method": "comparables_market_multiple_scorer",
    "cost_to_duplicate_method": "cost_to_duplicate_scorer",
}
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
docker_ocr_client_factory_from_config = None
extract_document_folder = None
RagConfig = None
skill_knowledge_rag_config = None
skill_prepare_blueprint_knowledge_rag = None
skill_public_rag_state = None
skill_resolve_blueprint_knowledge_dir = None
skill_retrieve_knowledge_rag_context = None
skill_require_ready_knowledge_rag = None
EVENT_LOCK = threading.Lock()
TRACE_LOCK = threading.Lock()
SKILL_LOAD_LOCK = threading.Lock()
NON_SUBSTANTIVE_SOURCE_STATUSES = {"planned", "configured_reference", "disabled", "skill_unavailable", "failed", "blocked", "warning", "error", "budget_exhausted"}
WARNING_SOURCE_STATUSES = {"failed", "blocked", "skill_unavailable", "warning", "budget_exhausted"}
DEFAULT_ACTION_BUDGET = 1000
DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS = 10.0
DEFAULT_ACTOR_REVIEW_LLM_ACTOR_IDS = [
    "research_reconciler",
    "score_consistency_auditor",
    "company_report_writer",
    "batch_index_writer",
]
KNOWLEDGE_PLAYBOOK_RELATIVE_PATH = "knowledge/startup_research_playbook.md"
DEFAULT_AGENTIC_RESEARCH_AGENT_IDS = [
    "research_planner",
    "company_identity_researcher",
    "funding_researcher",
    "market_comp_researcher",
    "traction_verifier",
    "rendered_page_researcher",
]
DEFAULT_AGENTIC_RESEARCH_TOOLS = ["browser_search", "browser_page", "rendered_browser_page", "finish"]
PROFILE_DOMAINS = ("linkedin.com", "crunchbase.com", "x.com", "twitter.com", "angellist.com", "wellfound.com")
APP_STORE_DOMAINS = ("apps.apple.com", "play.google.com", "chromewebstore.google.com")
PACKAGE_DOMAINS = ("npmjs.com", "pypi.org", "rubygems.org", "crates.io", "packagist.org")
JS_HEAVY_DOMAINS = ("crunchbase.com", "linkedin.com", "x.com", "twitter.com")
SOURCE_QUALITY_LABELS = {
    "local_claim",
    "public_confirmation",
    "public_conflict",
    "blocked",
    "thin_signal",
    "technical_signal",
    "market_context",
}
VC_METHOD_GUIDANCE = {
    "berkus_method": {
        "label": "Berkus Method",
        "memory_hook": "5 buckets",
        "purpose": "quick pre-revenue value proxy based on risk reduction",
    },
    "scorecard_bill_payne_method": {
        "label": "Scorecard / Bill Payne Method",
        "memory_hook": "weighted comparison",
        "purpose": "compare against similar early-stage startups using weighted factors",
    },
    "risk_factor_summation_method": {
        "label": "Risk Factor Summation Method",
        "memory_hook": "risk checklist",
        "purpose": "adjust a baseline view for evidenced major risk categories",
    },
    "venture_capital_method": {
        "label": "VC Method",
        "memory_hook": "exit-return math",
        "purpose": "test whether exit, ownership, and return assumptions can support venture returns",
    },
    "first_chicago_method": {
        "label": "First Chicago Method",
        "memory_hook": "scenario weighting",
        "purpose": "combine downside, base, and upside scenarios into a probability-weighted view",
    },
    "comparables_market_multiple_method": {
        "label": "Comparable Transactions / Market Multiples",
        "memory_hook": "market benchmark",
        "purpose": "anchor the company against similar companies, financings, exits, or multiples",
    },
    "cost_to_duplicate_method": {
        "label": "Cost-to-Duplicate Method",
        "memory_hook": "replacement cost",
        "purpose": "estimate what it would cost to rebuild the asset base as a floor proxy",
    },
}
JUDGE_RUBRIC = [
    "method_correctness",
    "evidence_grounding",
    "assumption_clarity",
    "missing_evidence_honesty",
    "financial_reasoning_quality",
    "report_usefulness_without_investment_advice",
]

RESEARCH_AGENT_PROMPT_SPECS = {
    "research_planner": {
        "mission": "Choose public-safe diligence lanes, target public URLs, and query families before stage research begins.",
        "allowed_evidence": ["local claim summaries", "RAG playbook refs", "public source metadata", "company name only"],
        "forbidden_inputs": ["raw confidential packet text", "private financial models", "personal contact details"],
        "rag_query_terms": ["VC diligence lane planning", "public-safe startup research", "source quality labels", "evidence gaps"],
        "tool_policy": "Prefer search queries that expose official sites, profiles, docs, pricing, funding, and traction; never search private packet text.",
        "failure_conditions": ["No RAG refs when RAG is required", "Queries include private/confidential input", "Plan does not explain why each lane matters"],
    },
    "company_identity_researcher": {
        "mission": "Verify company identity, official website, public profile pages, founder/company public profiles, and naming conflicts.",
        "allowed_evidence": ["official website", "LinkedIn or Crunchbase company profile", "public founder/company profile", "public docs or repository"],
        "forbidden_inputs": ["private founder contact info", "unpublished customer lists", "raw deck text"],
        "rag_query_terms": ["company identity verification", "official website", "founder profile", "public profile conflict"],
        "tool_policy": "Prioritize official site/profile pages, then public search for conflicts or aliases.",
        "failure_conditions": ["No official/public identity source attempted", "Profile conflict not recorded", "No RAG refs when RAG is required"],
    },
    "funding_researcher": {
        "mission": "Find public funding, accelerator, investor, grant, milestone, and financing confirmation evidence without trusting pitch claims as confirmation.",
        "allowed_evidence": ["public funding announcements", "accelerator pages", "grant pages", "investor portfolio pages", "SEC/public filings when relevant"],
        "forbidden_inputs": ["unpublished term sheets", "private investor emails", "raw cap table details"],
        "rag_query_terms": ["startup funding evidence", "accelerator investor grant milestone", "public confirmation vs pitch claim"],
        "tool_policy": "Search public funding and accelerator sources; distinguish unconfirmed local claims from public confirmations.",
        "failure_conditions": ["Pitch claim treated as public confirmation", "No public funding/accelerator search attempted", "No RAG refs when RAG is required"],
    },
    "market_comp_researcher": {
        "mission": "Gather category, competitors, market context, public-company comparables, and evidence quality for comparable analysis.",
        "allowed_evidence": ["market category sources", "competitor sites", "public company context", "industry reports or government statistics"],
        "forbidden_inputs": ["private competitor lists copied from packet text", "investment recommendation labels"],
        "rag_query_terms": ["market category comparables", "competitor evidence quality", "VC comparables method"],
        "tool_policy": "Search category and competitor context; prefer public/government/company sources over generic blogs.",
        "failure_conditions": ["No comparable/category evidence attempted", "Comparable quality not labeled", "No RAG refs when RAG is required"],
    },
    "traction_verifier": {
        "mission": "Verify customers, partnerships, launch, pricing, usage, app/package adoption, repositories, and other public traction signals.",
        "allowed_evidence": ["customer/partner pages", "pricing pages", "release notes", "app/package stats", "GitHub or docs activity", "press pages"],
        "forbidden_inputs": ["private customer names from packets", "nonpublic revenue data", "recommendation labels"],
        "rag_query_terms": ["startup traction verification", "pricing launch adoption public evidence", "GitHub package adoption"],
        "tool_policy": "Use public signals only; mark thin, blocked, or missing traction honestly.",
        "failure_conditions": ["Private traction claim exposed in query", "No traction signal attempted", "No RAG refs when RAG is required"],
    },
    "rendered_page_researcher": {
        "mission": "Inspect JS-heavy or blocked public rendered pages only when lightweight fetch is insufficient; record blocked/login/robots states without bypassing.",
        "allowed_evidence": ["public rendered pages", "blocked/login status", "visible profile metadata"],
        "forbidden_inputs": ["login bypass", "robots circumvention", "credentialed pages", "private packet text"],
        "rag_query_terms": ["rendered page review", "JS-heavy public startup profiles", "blocked page handling"],
        "tool_policy": "Use rendered browser only for public pages selected by previous stages; never bypass access controls.",
        "failure_conditions": ["Rendered browser used for private or credentialed content", "Blocked state omitted", "No RAG refs when RAG is required"],
    },
}

REVIEW_AGENT_PROMPT_SPECS = {
    "research_reconciler": {
        "mission": "Compare local claims against public sources and produce confirmations, conflicts, and missing-public-evidence items.",
        "focus": ["research_reconciliation", "source quality labels", "missing public evidence"],
    },
    "score_consistency_auditor": {
        "mission": "Check cross-method consistency, invalid scored/null states, unsupported assumptions, and missing method outputs.",
        "focus": ["method_coverage", "audit", "composite score consistency"],
    },
    "company_report_writer": {
        "mission": "Review per-company report usefulness, evidence traceability, and no-investment-advice boundaries.",
        "focus": ["analysis.md usefulness", "evidence traceability", "report-only language"],
    },
    "batch_index_writer": {
        "mission": "Review batch index coverage, skipped companies, run summary clarity, and navigation artifacts.",
        "focus": ["company_index", "run_summary", "skipped companies", "output files"],
    },
}

for _method_id, _scorer_id in SCORER_STAGE_BY_METHOD.items():
    REVIEW_AGENT_PROMPT_SPECS[_scorer_id] = {
        "mission": f"Review only the deterministic {_method_id} output against its method playbook, evidence refs, assumptions, and missing evidence.",
        "focus": [_method_id, "method_correctness", "evidence_grounding", "assumption_clarity"],
    }


def _workspace_root() -> Path | None:
    value = os.environ.get("MN_WORKSPACE_ROOT")
    if value:
        return Path(value).expanduser()
    for parent in Path(__file__).resolve().parents:
        if (parent / "mn-skills").exists():
            return parent
    return None


def _add_repo_paths() -> None:
    bundle_root = Path(__file__).resolve().parents[1]
    bundled_skills = bundle_root / "skills"
    if bundled_skills.exists():
        for skill_name in ("rag_skill",):
            candidate = bundled_skills / skill_name / "src"
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
    workspace = _workspace_root()
    if not workspace:
        return
    for skill_name in ("blueprint_support_skill", "llm_ocr_skill", "w3m_browser_skill", "web_browser_skill", "rag_skill"):
        candidate = workspace / "mn-skills" / skill_name / "src"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_add_repo_paths()

try:
    from mn_blueprint_support import get_actor_llm_client
    from mn_blueprint_support import llm_usage
    from mn_blueprint_support import resolve_actor_specs
    from mn_blueprint_support import run_actor_reviews
    from mn_blueprint_support import start_agent_beacon_thread as imported_start_agent_beacon_thread

    start_agent_beacon_thread = imported_start_agent_beacon_thread
except Exception:  # pragma: no cover - optional runtime support
    class _FallbackActorLLM:
        provider = "fallback"

        def __init__(self, model: str = "unknown") -> None:
            self.model = model
            self.calls = 0
            self.fallback_calls = 0

        def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
            del system_prompt, user_prompt
            self.calls += 1
            self.fallback_calls += 1
            response = dict(fallback)
            response.setdefault("provider", self.provider)
            response.setdefault("model", self.model)
            return response

    def resolve_actor_specs(
        config: dict[str, Any] | None,
        *,
        actor_ids: list[str] | tuple[str, ...] | set[str] | None = None,
        include_default: bool = False,
    ) -> dict[str, dict[str, Any]]:
        llm_config = (config or {}).get("llm") if isinstance((config or {}).get("llm"), dict) else {}
        agents = llm_config.get("agents") if isinstance(llm_config.get("agents"), dict) else {}
        selected = list(actor_ids or [key for key in agents if include_default or key != "default"])
        return {str(actor_id): dict(agents.get(str(actor_id)) or {}) for actor_id in selected}

    def get_actor_llm_client(config: dict[str, Any] | None, llm_client: Any | None = None) -> Any:
        if llm_client is not None:
            return llm_client
        llm_config = (config or {}).get("llm") if isinstance((config or {}).get("llm"), dict) else {}
        return _FallbackActorLLM(str(llm_config.get("model") or "unknown"))

    def llm_usage(llm: Any) -> dict[str, Any]:
        return {
            "provider": getattr(llm, "provider", "unknown"),
            "model": getattr(llm, "model", "unknown"),
            "calls": int(getattr(llm, "calls", 0) or 0),
            "fallback_calls": int(getattr(llm, "fallback_calls", 0) or 0),
        }

    def run_actor_reviews(
        *,
        config: dict[str, Any],
        llm: Any,
        actor_ids: list[str] | tuple[str, ...] | set[str],
        state: dict[str, Any],
        task: str,
        context: dict[str, Any],
        event_sink: Any | None = None,
    ) -> dict[str, Any]:
        findings = state.setdefault("actor_findings", {})
        for actor_id in actor_ids:
            fallback = {
                "actor_id": actor_id,
                "summary": "Actor review unavailable; deterministic VC report artifacts were preserved.",
                "findings": [],
                "risks": [],
                "confidence": 0.35,
            }
            try:
                finding = llm.generate_json(system_prompt=str(actor_id), user_prompt=json.dumps({"task": task, "context": context}, default=str), fallback=fallback)
            except Exception:
                finding = fallback
            findings[str(actor_id)] = finding
            if event_sink is not None:
                append_event(Path(event_sink), "actor_activity", {"agent_id": str(actor_id), "status": "completed", "summary": finding.get("summary")})
        return findings


try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document_folder
except Exception:  # pragma: no cover - optional runtime support
    docker_ocr_client_factory_from_config = None
    extract_document_folder = None


def _load_w3m_browser_skill() -> None:
    global W3mBrowserConfig, browse_url, build_search_url, research_topic
    if W3mBrowserConfig is not None and browse_url is not None and research_topic is not None:
        return
    with SKILL_LOAD_LOCK:
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
    with SKILL_LOAD_LOCK:
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


def _looks_like_sandbox_home(path: Path) -> bool:
    raw = str(path)
    return raw in {"/root", "/tmp", "/var/root"} or raw.startswith(
        ("/root/", "/tmp/", "/private/tmp/", "/var/root/", "/var/folders/", "/private/var/folders/")
    )


def _home_from_mirror_neuron_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    parts = path.parts
    if ".mn" not in parts:
        return None
    marker_index = parts.index(".mn")
    if marker_index <= 0:
        return None
    home = Path(*parts[:marker_index])
    return home if str(home) and not _looks_like_sandbox_home(home) else None


def _home_from_macos_users_dir() -> Path | None:
    users_dir = Path("/Users")
    if not users_dir.exists():
        return None
    names = [
        os.environ.get("SUDO_USER"),
        os.environ.get("LOGNAME"),
        os.environ.get("USER"),
    ]
    for name in names:
        if not name or name in {"root", "daemon", "nobody"}:
            continue
        candidate = users_dir / name
        if candidate.exists() and not _looks_like_sandbox_home(candidate):
            return candidate
    candidates = [
        path
        for path in users_dir.iterdir()
        if path.is_dir()
        and path.name not in {"Shared", "Guest", "Deleted Users"}
        and not path.name.startswith(".")
        and ((path / "Downloads").exists() or (path / ".mn").exists())
    ]
    if len(candidates) == 1 and not _looks_like_sandbox_home(candidates[0]):
        return candidates[0]
    return None


def runtime_user_home() -> Path:
    for env_name in ("MN_OUTPUT_HOME", "MN_USER_HOME", "OTTERDESK_USER_HOME"):
        value = os.environ.get(env_name)
        if value:
            return Path(value).expanduser()
    for env_name in ("MN_RUN_DIR", "MN_RUNS_ROOT", "MN_HOME", "OTTERDESK_RUN_DIR", "OTTERDESK_RUNS_ROOT"):
        home = _home_from_mirror_neuron_path(os.environ.get(env_name))
        if home:
            return home
    expanded = Path("~").expanduser()
    if not _looks_like_sandbox_home(expanded):
        return expanded
    try:
        import pwd

        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        if account_home and not _looks_like_sandbox_home(account_home):
            return account_home
    except Exception:
        pass
    macos_home = _home_from_macos_users_dir()
    if macos_home:
        return macos_home
    return expanded


def expand_runtime_path(value: str | Path) -> Path:
    raw = str(value)
    if raw == "~":
        return runtime_user_home()
    if raw.startswith("~/") or raw.startswith("~\\"):
        return runtime_user_home() / raw[2:]
    return Path(raw).expanduser()


def resolve_existing_path(value: str | Path, search_roots: list[Path]) -> Path:
    candidate = expand_runtime_path(value)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    candidates = [candidate]
    raw_parts = candidate.parts
    if raw_parts and raw_parts[0] == BLUEPRINT_ID:
        stripped = Path(*raw_parts[1:]) if len(raw_parts) > 1 else Path("")
        candidates.extend(root / stripped for root in search_roots)
    candidates.extend(root / candidate for root in search_roots)
    for possible in candidates:
        if possible.exists():
            return possible
    return candidate


def resolve_run_dir(output_folder: Path, run_id: str, runs_root: str | Path | None = None) -> Path:
    if not runs_root:
        env_run_dir = os.environ.get("MN_RUN_DIR")
        if env_run_dir:
            return expand_runtime_path(env_run_dir)
    resolved_runs_root = runs_root or os.environ.get("MN_RUNS_ROOT")
    if resolved_runs_root:
        return expand_runtime_path(resolved_runs_root) / run_id
    return output_folder / "runs" / run_id


def vc_knowledge_search_roots(blueprint_dir: Path) -> list[Path]:
    roots = [blueprint_dir]
    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        roots.append(Path(bundle_dir).expanduser())
    script_path = Path(__file__).resolve()
    roots.extend([script_path.parents[1], script_path.parents[2], script_path.parents[3]])
    unique_roots = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def load_vc_knowledge(blueprint_dir: Path) -> dict[str, Any]:
    playbook_path = next(
        (
            root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH
            for root in vc_knowledge_search_roots(blueprint_dir)
            if (root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH).exists()
        ),
        blueprint_dir / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
    )
    try:
        content = playbook_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""
    return {
        "id": "vc_startup_research_playbook",
        "title": "VC Startup Research And Method Playbook",
        "path": KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
        "resolved_path": str(playbook_path),
        "sha256": digest,
        "content": content[:16000],
        "method_guidance": VC_METHOD_GUIDANCE,
        "judge_rubric": JUDGE_RUBRIC,
        "domain_guard": "Use VC analysis knowledge only; ignore unrelated non-VC domain knowledge.",
    }


def _load_rag_skill() -> None:
    global RagConfig, skill_knowledge_rag_config, skill_prepare_blueprint_knowledge_rag
    global skill_public_rag_state, skill_resolve_blueprint_knowledge_dir, skill_retrieve_knowledge_rag_context
    global skill_require_ready_knowledge_rag
    if (
        RagConfig is not None
        and skill_knowledge_rag_config is not None
        and skill_prepare_blueprint_knowledge_rag is not None
        and skill_public_rag_state is not None
        and skill_resolve_blueprint_knowledge_dir is not None
        and skill_retrieve_knowledge_rag_context is not None
        and skill_require_ready_knowledge_rag is not None
    ):
        return
    with SKILL_LOAD_LOCK:
        if (
            RagConfig is not None
            and skill_knowledge_rag_config is not None
            and skill_prepare_blueprint_knowledge_rag is not None
            and skill_public_rag_state is not None
            and skill_resolve_blueprint_knowledge_dir is not None
            and skill_retrieve_knowledge_rag_context is not None
            and skill_require_ready_knowledge_rag is not None
        ):
            return
        try:
            from mn_rag_skill import RagConfig as imported_RagConfig
            from mn_rag_skill import knowledge_rag_config as imported_knowledge_rag_config
            from mn_rag_skill import prepare_blueprint_knowledge_rag as imported_prepare_blueprint_knowledge_rag
            from mn_rag_skill import public_rag_state as imported_public_rag_state
            from mn_rag_skill import require_ready_knowledge_rag as imported_require_ready_knowledge_rag
            from mn_rag_skill import resolve_blueprint_knowledge_dir as imported_resolve_blueprint_knowledge_dir
            from mn_rag_skill import retrieve_knowledge_rag_context as imported_retrieve_knowledge_rag_context
        except Exception as exc:
            raise RuntimeError(f"mn_rag_skill unavailable: {exc}") from exc
        RagConfig = imported_RagConfig
        skill_knowledge_rag_config = imported_knowledge_rag_config
        skill_prepare_blueprint_knowledge_rag = imported_prepare_blueprint_knowledge_rag
        skill_public_rag_state = imported_public_rag_state
        skill_resolve_blueprint_knowledge_dir = imported_resolve_blueprint_knowledge_dir
        skill_retrieve_knowledge_rag_context = imported_retrieve_knowledge_rag_context
        skill_require_ready_knowledge_rag = imported_require_ready_knowledge_rag


def knowledge_rag_config(config: dict[str, Any]) -> dict[str, Any]:
    _load_rag_skill()
    return skill_knowledge_rag_config(config)


def resolve_knowledge_dir(blueprint_dir: Path, active_knowledge: dict[str, Any]) -> Path:
    _load_rag_skill()
    return skill_resolve_blueprint_knowledge_dir(blueprint_dir, active_knowledge=active_knowledge)


def prepare_knowledge_rag(
    *,
    blueprint_dir: Path,
    resolved_config: dict[str, Any],
    active_knowledge: dict[str, Any],
    run_dir: Path | None = None,
) -> dict[str, Any]:
    raw = resolved_config.get("knowledge_rag") if isinstance(resolved_config.get("knowledge_rag"), dict) else {}
    if fake_llm_mode_enabled(resolved_config):
        return {
            "enabled": False,
            "status": "disabled_for_fake_llm",
            "required": False,
            "warnings": [
                {
                    "kind": "knowledge_rag",
                    "status": "disabled_for_fake_llm",
                    "message": "Knowledge RAG embedding calls are disabled during explicit fake-LLM smoke runs.",
                }
            ],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
                "required": False,
            },
        }
    if not bool(raw.get("enabled", True)):
        return {
            "enabled": False,
            "status": "disabled",
            "warnings": [],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
            },
        }
    try:
        _load_rag_skill()
    except Exception as exc:
        warning = {
            "kind": "knowledge_rag",
            "status": "knowledge_rag_failed",
            "message": "Knowledge RAG was enabled but Redis/vector indexing could not complete; no static playbook fallback was injected.",
            "error": str(exc),
        }
        state = {
            "enabled": bool(raw.get("enabled", True)),
            "status": "knowledge_rag_failed",
            "warnings": [warning],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
            },
        }
        append_event(run_dir, "tool_call_failed", {"tool": "knowledge_rag.index", "status": "knowledge_rag_failed", "error": str(exc)}) if run_dir else None
        return state

    def event_callback(event_type: str, payload: dict[str, Any]) -> None:
        if run_dir:
            append_event(run_dir, event_type, payload)

    return skill_prepare_blueprint_knowledge_rag(
        blueprint_id=BLUEPRINT_ID,
        blueprint_dir=blueprint_dir,
        config=resolved_config,
        active_knowledge=active_knowledge,
        event_callback=event_callback,
    )


def public_knowledge_rag_state(state: dict[str, Any] | None) -> dict[str, Any]:
    try:
        _load_rag_skill()
        return skill_public_rag_state(state)
    except Exception:
        if not state:
            return {"enabled": False, "status": "disabled"}
        return {key: value for key, value in state.items() if not key.startswith("_")}


def knowledge_rag_is_required(state: dict[str, Any] | None) -> bool:
    if not state or not state.get("enabled"):
        return False
    config = state.get("config") if isinstance(state.get("config"), dict) else {}
    value = state.get("required", config.get("required"))
    return bool(value) if isinstance(value, bool) else str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def require_ready_rag(
    knowledge_rag: dict[str, Any] | None,
    *,
    stage: str = "",
    company: str = "",
    context: dict[str, Any] | None = None,
    min_citations: int = 0,
    run_dir: Path | None = None,
) -> dict[str, Any] | None:
    if not knowledge_rag_is_required(knowledge_rag):
        return context if context is not None else knowledge_rag
    _load_rag_skill()
    with observed_operation(
        run_dir,
        phase="knowledge_rag",
        operation="require_ready",
        stage=stage,
        company=company,
        min_citations=min_citations,
        citation_count=len((context or {}).get("citations") or []) if isinstance(context, dict) else None,
        context_chars=len(str((context or {}).get("context") or "")) if isinstance(context, dict) else None,
    ):
        return skill_require_ready_knowledge_rag(
            knowledge_rag,
            stage=stage,
            company=company,
            context=context,
            min_citations=min_citations,
        )


def active_knowledge_for_prompt(active_knowledge: dict[str, Any], knowledge_rag: dict[str, Any] | None) -> dict[str, Any]:
    if (knowledge_rag or {}).get("enabled"):
        ref = active_knowledge_reference(active_knowledge)
        ref["domain_guard"] = active_knowledge.get("domain_guard")
        ref["content_retrieval"] = "redis_rag"
        return ref
    return active_knowledge


def retrieve_knowledge_rag_context(
    *,
    knowledge_rag: dict[str, Any] | None,
    query: str,
    stage: str = "",
    company: str = "",
    run_dir: Path | None = None,
) -> dict[str, Any]:
    metadata = {
        "stage": stage,
        "company": company,
        "query_hash": stable_text_hash(query),
        "query_chars": len(query or ""),
    }
    try:
        _load_rag_skill()
        with observed_operation(run_dir, phase="knowledge_rag", operation="retrieve", **metadata) as op:
            context = skill_retrieve_knowledge_rag_context(
                knowledge_rag=knowledge_rag,
                query=query,
                stage=stage,
                company=company,
            )
            if isinstance(context, dict):
                op.close(
                    "completed",
                    rag_status=context.get("status"),
                    citation_count=len(context.get("citations") or []),
                    context_chars=len(str(context.get("context") or "")),
                )
            return context
    except Exception as exc:
        append_observation_record(
            run_dir,
            "observability_operation_failed",
            {
                "phase": "knowledge_rag",
                "operation": "retrieve",
                "status": "failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
                **metadata,
            },
        )
        return {
            "enabled": bool((knowledge_rag or {}).get("enabled")),
            "status": "knowledge_rag_failed",
            "query": query,
            "context": "",
            "citations": [],
            "chunks": [],
            "warnings": [
                {
                    "kind": "knowledge_rag",
                    "status": "knowledge_rag_failed",
                    "message": f"Knowledge RAG retrieval failed for {stage or 'prompt'}; prompt continued without retrieved knowledge context.",
                    "error": str(exc),
                }
            ],
            "stage": stage,
            "company": company,
        }


def rag_ref_values(value: Any) -> list[Any]:
    refs: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"rag_refs", "rag_ref", "citation_refs", "citations"}:
                if isinstance(item, list):
                    refs.extend(item)
                elif item not in (None, ""):
                    refs.append(item)
            else:
                refs.extend(rag_ref_values(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(rag_ref_values(item))
    return refs


def validate_llm_rag_refs(decision: dict[str, Any], *, knowledge_rag: dict[str, Any] | None, stage: str, company: str = "") -> None:
    if knowledge_rag_is_required(knowledge_rag) and not rag_ref_values(decision):
        label = f"{stage}{f' / {company}' if company else ''}"
        raise RuntimeError(f"Required RAG citation refs missing from LLM output for {label}.")


def citation_ref_values(rag_context: dict[str, Any] | None, *, limit: int = 3) -> list[Any]:
    refs = []
    for citation in (rag_context or {}).get("citations") or []:
        if isinstance(citation, dict) and citation.get("ref") not in (None, ""):
            refs.append(citation.get("ref"))
    return refs[:limit]


def active_knowledge_reference(active_knowledge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": active_knowledge.get("id"),
        "title": active_knowledge.get("title"),
        "path": active_knowledge.get("path"),
        "sha256": active_knowledge.get("sha256"),
        "method_memory_hooks": {
            method_id: guidance["memory_hook"]
            for method_id, guidance in (active_knowledge.get("method_guidance") or {}).items()
            if isinstance(guidance, dict) and guidance.get("memory_hook")
        },
        "judge_rubric": list(active_knowledge.get("judge_rubric") or []),
    }


def actor_review_unavailable_findings(actor_ids: list[str], error: Exception | str) -> dict[str, Any]:
    message = str(error) or "Actor review unavailable."
    return {
        actor_id: {
            "actor_id": actor_id,
            "summary": "Actor review unavailable; deterministic VC report artifacts were preserved.",
            "findings": [
                {
                    "severity": "warning",
                    "message": "LLM actor review failed after deterministic reports were generated.",
                    "detail": message,
                }
            ],
            "risks": [],
            "confidence": 0.35,
            "provider": "actor_review_unavailable",
            "budget_status": "not_applicable",
        }
        for actor_id in actor_ids
    }


class ActionBudget:
    def __init__(self, default_actions: int = DEFAULT_ACTION_BUDGET) -> None:
        self.budget = max(0, int(default_actions or 0))
        self.used = 0
        self.actions: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def start(
        self,
        *,
        action_type: str,
        stage: str,
        company: str = "",
        tool: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self.lock:
            if self.used >= self.budget:
                self.actions.append(
                    {
                        "action_index": len(self.actions) + 1,
                        "cost": 0,
                        "budget": self.budget,
                        "used": self.used,
                        "remaining": 0,
                        "action_type": action_type,
                        "stage": stage,
                        "company": company,
                        "tool": tool,
                        "status": "budget_exhausted",
                        "metadata": metadata or {},
                        "recorded_at": utc_now_iso(),
                    }
                )
                return None
            self.used += 1
            action = {
                "action_index": len(self.actions) + 1,
                "cost": 1,
                "budget": self.budget,
                "used": self.used,
                "remaining": max(0, self.budget - self.used),
                "action_type": action_type,
                "stage": stage,
                "company": company,
                "tool": tool,
                "status": "started",
                "metadata": metadata or {},
                "recorded_at": utc_now_iso(),
            }
            self.actions.append(action)
            return action

    def complete(self, action: dict[str, Any] | None, status: str, metadata: dict[str, Any] | None = None) -> None:
        if action is None:
            return
        with self.lock:
            action["status"] = status
            if metadata:
                action.setdefault("metadata", {}).update(metadata)
            action["completed_at"] = utc_now_iso()

    def summary(self, *, include_actions: bool = True) -> dict[str, Any]:
        with self.lock:
            summary = {
                "budget": self.budget,
                "used": self.used,
                "remaining": max(0, self.budget - self.used),
                "exhausted": self.used >= self.budget,
            }
            if include_actions:
                summary["actions"] = [dict(action) for action in self.actions]
            return summary


class LlmCallLimiter:
    def __init__(self, *, max_concurrent_calls: int = 1, min_interval_seconds: float = 0.0) -> None:
        self.max_concurrent_calls = max(1, int(max_concurrent_calls or 1))
        self.min_interval_seconds = max(0.0, float(min_interval_seconds or 0.0))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent_calls)
        self._interval_lock = threading.Lock()
        self._next_allowed_at = 0.0

    def acquire(self) -> float:
        self._semaphore.acquire()
        if self.min_interval_seconds <= 0:
            return 0.0
        with self._interval_lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_allowed_at - now)
            self._next_allowed_at = max(now, self._next_allowed_at) + self.min_interval_seconds
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        return wait_seconds

    def release(self) -> None:
        self._semaphore.release()

    def config_summary(self) -> dict[str, Any]:
        return {
            "max_concurrent_calls": self.max_concurrent_calls,
            "min_interval_seconds": self.min_interval_seconds,
        }


def build_llm_call_limiter(config: dict[str, Any]) -> LlmCallLimiter:
    backpressure = config.get("backpressure") if isinstance(config.get("backpressure"), dict) else {}
    llm_config = backpressure.get("llm") if isinstance(backpressure.get("llm"), dict) else {}
    if fake_llm_mode_enabled(config):
        return LlmCallLimiter(
            max_concurrent_calls=bounded_int(llm_config.get("max_concurrent_calls"), default=8, minimum=1, maximum=8),
            min_interval_seconds=0.0,
        )
    return LlmCallLimiter(
        max_concurrent_calls=bounded_int(llm_config.get("max_concurrent_calls"), default=1, minimum=1, maximum=8),
        min_interval_seconds=float(llm_config.get("min_interval_seconds") or 0.0),
    )


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": payload}
    with EVENT_LOCK:
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def stable_text_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def _safe_observation_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"prompt", "system_prompt", "user_prompt", "response", "context", "raw_text", "document_text", "text", "content"}:
                cleaned[f"{key_text}_redacted"] = True
                continue
            cleaned[key_text] = _safe_observation_value(item, depth=depth + 1)
        return cleaned
    if isinstance(value, list):
        return [_safe_observation_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return value if len(value) <= 1000 else value[:1000] + "...[truncated]"
    return value


def observation_payload(**metadata: Any) -> dict[str, Any]:
    return _safe_observation_value({key: value for key, value in metadata.items() if value is not None})


def append_observation_record(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": observation_payload(**payload)}
    with TRACE_LOCK:
        with (run_dir / "llm_rag_trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    append_event(run_dir, event_type, record["payload"])


class ObservedOperation:
    def __init__(
        self,
        run_dir: Path | None,
        *,
        phase: str,
        operation: str,
        heartbeat_seconds: float = DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.phase = phase
        self.operation = operation
        self.heartbeat_seconds = max(float(heartbeat_seconds or 0), 0.0)
        self.operation_id = f"{slugify(phase)}-{slugify(operation)}-{uuid.uuid4().hex[:8]}"
        self.metadata = dict(metadata or {})
        self.started_at_monotonic = 0.0
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._closed = False

    def __enter__(self) -> "ObservedOperation":
        self.started_at_monotonic = time.monotonic()
        append_observation_record(self.run_dir, "observability_operation_started", self._payload(status="started"))
        if self.run_dir is not None and self.heartbeat_seconds > 0:
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name=f"vc-observe-{self.operation_id}", daemon=True)
            self._heartbeat_thread.start()
        return self

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.heartbeat_seconds):
            append_observation_record(self.run_dir, "observability_operation_heartbeat", self._payload(status="running"))

    def _payload(self, *, status: str, **metadata: Any) -> dict[str, Any]:
        elapsed_ms = round(max(time.monotonic() - self.started_at_monotonic, 0.0) * 1000, 2) if self.started_at_monotonic else 0.0
        return {
            "operation_id": self.operation_id,
            "phase": self.phase,
            "operation": self.operation,
            "status": status,
            "elapsed_ms": elapsed_ms,
            **self.metadata,
            **metadata,
        }

    def heartbeat(self, **metadata: Any) -> None:
        append_observation_record(self.run_dir, "observability_operation_heartbeat", self._payload(status="running", **metadata))

    def close(self, status: str = "completed", **metadata: Any) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=0.2)
        event_type = "observability_operation_completed" if status == "completed" else "observability_operation_failed"
        append_observation_record(self.run_dir, event_type, self._payload(status=status, **metadata))

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> bool:
        if exc is not None:
            self.close("failed", error=str(exc), error_type=type(exc).__name__)
        else:
            self.close("completed")
        return False


def observed_operation(
    run_dir: Path | None,
    *,
    phase: str,
    operation: str,
    heartbeat_seconds: float = DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS,
    **metadata: Any,
) -> ObservedOperation:
    return ObservedOperation(run_dir, phase=phase, operation=operation, heartbeat_seconds=heartbeat_seconds, metadata=metadata)


class BudgetedLLM:
    def __init__(
        self,
        llm: Any,
        action_budget: ActionBudget,
        *,
        require_live: bool = False,
        limiter: LlmCallLimiter | None = None,
        run_dir: Path | None = None,
        heartbeat_seconds: float = DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS,
    ) -> None:
        self._llm = llm
        self._action_budget = action_budget
        self._require_live = require_live
        self._limiter = limiter or LlmCallLimiter()
        self._run_dir = run_dir
        self._heartbeat_seconds = heartbeat_seconds

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        actor_id = str(fallback.get("actor_id") or system_prompt or "actor_review")
        provider_name = getattr(self._llm, "provider", "unknown")
        model_name = getattr(self._llm, "model", "unknown")
        prompt_metadata = {
            "agent_id": actor_id,
            "provider": provider_name,
            "model": model_name,
            "system_prompt_chars": len(system_prompt or ""),
            "user_prompt_chars": len(user_prompt or ""),
            "prompt_hash": stable_text_hash(f"{system_prompt}\n{user_prompt}"),
            "budget_before": self._action_budget.summary(include_actions=False),
        }
        with observed_operation(
            self._run_dir,
            phase="llm_call",
            operation="actor_llm.generate_json",
            heartbeat_seconds=self._heartbeat_seconds,
            **prompt_metadata,
        ) as op:
            action = self._action_budget.start(
                action_type="llm_call",
                stage=actor_id,
                tool="actor_llm",
                metadata={**prompt_metadata, "budget_before": None},
            )
            if action is None:
                op.close("failed", budget_status="budget_exhausted", budget_after=self._action_budget.summary(include_actions=False))
                if self._require_live:
                    raise RuntimeError("Required live LLM call could not run because the VC Assistant action budget was exhausted.")
                response = dict(fallback)
                response["summary"] = response.get("summary") or "Actor review skipped because the VC Assistant action budget was exhausted."
                response.setdefault("findings", [])
                response.setdefault("risks", [])
                response["provider"] = "budget_exhausted"
                response["model"] = model_name
                response["budget_status"] = "budget_exhausted"
                return response
            acquired = False
            limiter_wait_seconds = 0.0
            try:
                limiter_wait_seconds = self._limiter.acquire()
                acquired = True
                op.heartbeat(limiter_wait_seconds=round(limiter_wait_seconds, 3), status_detail="calling_model")
                response = self._llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
            except Exception as exc:
                self._action_budget.complete(action, "failed", {"error": str(exc), "limiter_wait_seconds": round(limiter_wait_seconds, 3)})
                op.close(
                    "failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    limiter_wait_seconds=round(limiter_wait_seconds, 3),
                    budget_after=self._action_budget.summary(include_actions=False),
                )
                if self._require_live:
                    raise RuntimeError(f"Required live LLM call failed for {actor_id}: {exc}") from exc
                response = dict(fallback)
                response["summary"] = response.get("summary") or "Actor review unavailable; deterministic VC report artifacts were preserved."
                response.setdefault("findings", [])
                response.setdefault("risks", [])
                response["provider"] = "actor_review_unavailable"
                response["model"] = model_name
                response["error"] = str(exc)
                response["budget_status"] = "llm_call_failed"
                return response
            finally:
                if acquired:
                    self._limiter.release()
            provider = str(response.get("provider") or provider_name) if isinstance(response, dict) else ""
            budget_status = str(response.get("budget_status") or "") if isinstance(response, dict) else ""
            response_chars = len(json.dumps(response, default=str)) if isinstance(response, dict) else len(str(response))
            if self._require_live and (not provider_is_live(provider) or budget_status in {"budget_exhausted", "llm_call_failed"}):
                self._action_budget.complete(action, "failed", {"provider": provider, "budget_status": budget_status, "limiter_wait_seconds": round(limiter_wait_seconds, 3)})
                op.close(
                    "failed",
                    provider=provider,
                    budget_status=budget_status or "non_live_provider",
                    response_chars=response_chars,
                    limiter_wait_seconds=round(limiter_wait_seconds, 3),
                    budget_after=self._action_budget.summary(include_actions=False),
                )
                raise RuntimeError(f"Required live LLM call for {actor_id} returned non-live provider '{provider or 'unknown'}'.")
            self._action_budget.complete(action, "completed", {"provider": provider, "response_chars": response_chars, "limiter_wait_seconds": round(limiter_wait_seconds, 3)})
            op.close(
                "completed",
                provider=provider,
                response_chars=response_chars,
                limiter_wait_seconds=round(limiter_wait_seconds, 3),
                budget_after=self._action_budget.summary(include_actions=False),
            )
            return response


def bounded_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 32) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def build_action_budget(config: dict[str, Any]) -> ActionBudget:
    research_budget = config.get("research_budget") if isinstance(config.get("research_budget"), dict) else {}
    return ActionBudget(default_actions=bounded_int(research_budget.get("default_actions"), default=DEFAULT_ACTION_BUDGET, minimum=0, maximum=100000))


def env_flag_enabled(name: str) -> bool:
    value = os.environ.get(name)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def value_is_fake_llm(value: Any) -> bool:
    return str(value or "").strip().lower() in {"fake", "mock", "stub"}


def explicit_fake_llm_mode_enabled() -> bool:
    if any(env_flag_enabled(name) for name in ("MN_FAKE_LLM", "MN_BLUEPRINT_FAKE_LLM", "OTTERDESK_FAKE_LLM", "MN_USE_FAKE_LLM")):
        return True
    return any(
        value_is_fake_llm(os.environ.get(name))
        for name in ("MN_BLUEPRINT_LLM_MODE", "MN_LLM_MODE", "MN_LLM_PROVIDER", "MN_BLUEPRINT_LLM_PROVIDER")
    )


def fake_llm_mode_enabled(config: dict[str, Any]) -> bool:
    if explicit_fake_llm_mode_enabled():
        return True
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    config_name = str(llm_config.get("default_config") or "primary")
    configs = llm_config.get("configs") if isinstance(llm_config.get("configs"), dict) else {}
    primary = configs.get(config_name) if isinstance(configs.get(config_name), dict) else {}
    if any(value_is_fake_llm(value) for value in (llm_config.get("mode"), llm_config.get("provider"), primary.get("mode"), primary.get("provider"))):
        return True
    return quick_test_mode_enabled(config) and bool(llm_config.get("quick_test_uses_fake", True))


def call_with_supported_kwargs(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return func(**kwargs)
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return func(**supported)


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


def _configured_llm_env(config: dict[str, Any]) -> dict[str, str]:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    config_name = str(llm_config.get("default_config") or "primary")
    configs = llm_config.get("configs") if isinstance(llm_config.get("configs"), dict) else {}
    primary = configs.get(config_name) if isinstance(configs.get(config_name), dict) else {}
    if fake_llm_mode_enabled(config):
        return {
            "MN_BLUEPRINT_LLM_MODE": "fake",
            "MN_LLM_PROVIDER": "fake",
            "MN_LLM_MODEL": str(llm_config.get("mock_model") or "fake-vc-actor"),
        }
    values = {
        "MN_BLUEPRINT_LLM_MODE": llm_config.get("mode"),
        "MN_LLM_PROVIDER": llm_config.get("provider") or primary.get("provider"),
        "MN_LLM_MODEL": llm_config.get("model") or primary.get("model"),
        "MN_LLM_API_BASE": llm_config.get("api_base") or primary.get("api_base"),
        "MN_LLM_TIMEOUT_SECONDS": llm_config.get("timeout_seconds") or primary.get("timeout_seconds"),
        "MN_LLM_MAX_TOKENS": llm_config.get("max_tokens") or primary.get("max_tokens"),
        "MN_LLM_NUM_RETRIES": llm_config.get("num_retries") or primary.get("num_retries"),
        "MN_LLM_RETRY_BACKOFF_SECONDS": llm_config.get("retry_backoff_seconds") or primary.get("retry_backoff_seconds"),
    }
    return {key: str(value) for key, value in values.items() if value not in (None, "")}


def _get_configured_actor_llm(config: dict[str, Any], llm_client: Any | None) -> Any:
    if llm_client is not None:
        return get_actor_llm_client(config, llm_client)
    llm_env = _configured_llm_env(config)
    previous = {key: os.environ.get(key) for key in llm_env}
    try:
        for key, value in llm_env.items():
            os.environ[key] = value
        return get_actor_llm_client(config, None)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def quick_test_mode_enabled(config: dict[str, Any]) -> bool:
    payload = (config.get("inputs") or {}).get("payload") if isinstance(config.get("inputs"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    env_value = os.environ.get("MN_QUICK_TEST") or os.environ.get("MN_BLUEPRINT_QUICK_TEST")
    if env_value is not None:
        return str(env_value).strip().lower() in {"1", "true", "yes", "on"}
    return bool((payload or {}).get("quick_test") or execution.get("quick_test"))


def llm_requires_live(config: dict[str, Any]) -> bool:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if fake_llm_mode_enabled(config) or quick_test_mode_enabled(config):
        return False
    value = llm_config.get("require_live", False)
    return bool(value) if isinstance(value, bool) else str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def provider_is_live(provider: str) -> bool:
    return str(provider or "").strip().lower() not in {
        "",
        "fallback",
        "fake",
        "mock",
        "actor_review_unavailable",
        "budget_exhausted",
        "unavailable",
        "disabled",
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown-company"


def host_from_url(value: str) -> str:
    try:
        return urlparse(value).netloc[:200]
    except Exception:
        return ""


def redactor(text: str) -> str:
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", text or "")
    value = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", value)
    value = re.sub(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED-PHONE]", value)
    return value


def safe_read_text(path: Path) -> tuple[str, list[str]]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return "", ["Non-text file requires OCR extraction."]
    try:
        return path.read_text(encoding="utf-8", errors="ignore"), []
    except Exception as exc:
        return "", [str(exc)]


class OcrRequiredError(RuntimeError):
    pass


def startup_packet_classifier(text: str, filename: str) -> str:
    del text, filename
    return "startup_packet"


def _document_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve())


def _llm_ocr_records_for_pdfs(folder: Path, pdf_paths: list[Path], config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not pdf_paths:
        return {}
    if extract_document_folder is None:
        raise OcrRequiredError("PDF startup packets require llm_ocr_skill, but the OCR extractor is unavailable.")

    resolved_pdf_keys = {_path_key(path) for path in pdf_paths}
    skill_config = {"input_skills": (config or {}).get("input_skills", {})}
    ocr_config = ((config or {}).get("input_skills") or {}).get("llm_ocr") or {}
    min_text_chars = int(ocr_config.get("min_text_chars") or 40)
    factory = docker_ocr_client_factory_from_config(skill_config) if docker_ocr_client_factory_from_config else None
    records_by_path: dict[str, dict[str, Any]] = {}

    for parent in sorted({path.parent for path in pdf_paths}):
        try:
            extracted_records = extract_document_folder(
                parent,
                classifier=startup_packet_classifier,
                redactor=redactor,
                llm_ocr_client_factory=factory,
                min_text_chars=min_text_chars,
            )
        except Exception as exc:
            raise OcrRequiredError(f"PDF OCR failed for {parent}: {exc}") from exc

        for record in extracted_records:
            raw_path = record.get("path")
            if not raw_path:
                continue
            key = _path_key(Path(str(raw_path)))
            if key in resolved_pdf_keys:
                records_by_path[key] = dict(record)

    missing = [str(path) for path in pdf_paths if _path_key(path) not in records_by_path]
    if missing:
        raise OcrRequiredError(f"PDF OCR returned no evidence for required input(s): {', '.join(missing)}")

    for path in pdf_paths:
        record = records_by_path[_path_key(path)]
        text = str(record.get("text") or "")
        warnings = record.get("warnings") if isinstance(record.get("warnings"), list) else []
        if bool(record.get("ocr_required")) or len(text.strip()) < min_text_chars:
            detail = "; ".join(str(warning) for warning in warnings if warning) or "OCR returned too little text."
            raise OcrRequiredError(f"PDF OCR did not produce usable text for {path}: {detail}")

    return records_by_path


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


def scan_documents(folder: Path, config: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    records_by_company: dict[str, list[dict[str, Any]]] = {}
    paths = _document_paths(folder)
    if not paths:
        return records_by_company
    pdf_paths = [path for path in paths if path.suffix.lower() == ".pdf"]
    ocr_records_by_path = _llm_ocr_records_for_pdfs(folder, pdf_paths, config)
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            text, warnings = safe_read_text(path)
            extraction_method = "embedded_text"
            ocr_required = False
        else:
            ocr_record = ocr_records_by_path[_path_key(path)]
            text = str(ocr_record.get("text") or "")
            raw_warnings = ocr_record.get("warnings")
            warnings = [str(warning) for warning in raw_warnings] if isinstance(raw_warnings, list) else []
            extraction_method = str(ocr_record.get("extraction_method") or "llm_ocr")
            ocr_required = bool(ocr_record.get("ocr_required"))
        redacted = redactor(text)
        company = infer_company_name(path, redacted, folder)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {
            "path": str(path),
            "filename": path.name,
            "company_name": company,
            "sha256": digest,
            "suffix": suffix,
            "text_preview": redacted[:1200],
            "character_count": len(redacted),
            "extraction_method": extraction_method,
            "ocr_required": ocr_required,
            "warnings": warnings,
        }
        records_by_company.setdefault(company, []).append(record)
    return records_by_company


def company_fingerprint(records: list[dict[str, Any]]) -> str:
    joined = "\n".join(sorted(str(record.get("sha256") or "") for record in records))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def load_watch_state(output_folder: Path) -> dict[str, Any]:
    state = read_json(output_folder / "watch_state.json")
    companies = state.get("companies")
    if not isinstance(companies, dict):
        state["companies"] = {}
    return state


def build_company_work_queue(company_records: dict[str, list[dict[str, Any]]], previous_state: dict[str, Any]) -> list[dict[str, Any]]:
    previous_companies = previous_state.get("companies") if isinstance(previous_state.get("companies"), dict) else {}
    queue = []
    for company, records in sorted(company_records.items(), key=lambda item: slugify(item[0])):
        slug = slugify(company)
        fingerprint = company_fingerprint(records)
        previous = previous_companies.get(slug) if isinstance(previous_companies.get(slug), dict) else {}
        unchanged = previous.get("fingerprint") == fingerprint
        queue.append(
            {
                "company_id": slug,
                "company_name": company,
                "company_slug": slug,
                "fingerprint": fingerprint,
                "document_count": len(records),
                "status": "unchanged_skipped" if unchanged else "new_or_changed",
                "previous_fingerprint": previous.get("fingerprint"),
                "source_refs": [record.get("path") for record in records],
            }
        )
    return queue


def update_watch_state(output_folder: Path, run_dir: Path, queue: list[dict[str, Any]]) -> dict[str, Any]:
    state = {
        "updated_at": utc_now_iso(),
        "companies": {
            item["company_slug"]: {
                "company_name": item["company_name"],
                "fingerprint": item["fingerprint"],
                "status": item["status"],
                "document_count": item["document_count"],
            }
            for item in queue
        },
    }
    write_json(output_folder / "watch_state.json", state)
    write_json(run_dir / "watch_state.json", state)
    return state


def load_cached_company_analysis(output_folder: Path, company: str) -> dict[str, Any] | None:
    analysis = read_json(output_folder / slugify(company) / "analysis.json")
    if analysis.get("company_name") != company:
        return None
    if not isinstance(analysis.get("methods"), dict):
        return None
    return analysis


def load_cached_research_ledger(output_folder: Path, company: str) -> dict[str, list[dict[str, Any]]] | None:
    ledger = read_json(output_folder / "research_ledgers" / f"{slugify(company)}.json")
    if not ledger:
        return None
    normalized: dict[str, list[dict[str, Any]]] = {}
    for stage in RESEARCH_STAGE_IDS:
        values = ledger.get(stage)
        normalized[stage] = values if isinstance(values, list) else []
    return normalized


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


def source_refs_from_records(records: list[dict[str, Any]]) -> list[str]:
    refs = []
    for record in records:
        value = str(record.get("filename") or record.get("path") or "")
        if value and value not in refs:
            refs.append(value)
    return refs


def source_refs_from_sources(sources: list[dict[str, Any]]) -> list[str]:
    refs = []
    for source in sources:
        value = str(source.get("url") or "")
        if value and value not in refs:
            refs.append(value)
    return refs


def is_substantive_public_source(source: dict[str, Any]) -> bool:
    status = str(source.get("status") or "").lower()
    url = str(source.get("url") or "")
    snippet = str(source.get("snippet") or "")
    if status in NON_SUBSTANTIVE_SOURCE_STATUSES:
        return False
    if not url.startswith(("http://", "https://")):
        return False
    return bool(snippet.strip())


def extract_domains(text: str) -> list[str]:
    domains = []
    for match in re.finditer(r"\b(?:https?://)?([a-z0-9-]+\.[a-z0-9.-]+)\b", text, flags=re.I):
        domain = match.group(1).lower().strip(".")
        if domain and domain not in domains and not domain.endswith(".txt"):
            domains.append(domain)
    return domains[:10]


def dedupe_list(items: list[str], limit: int = 20) -> list[str]:
    seen = []
    for item in items:
        normalized = str(item or "").strip()
        if normalized and normalized not in seen:
            seen.append(normalized)
        if len(seen) >= limit:
            break
    return seen


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
    return {
        "lane_id": lane_id,
        "reason": reason,
        "tools": tools,
        "queries": dedupe_list(queries, 8),
        "target_urls": dedupe_list(target_urls or [], 20),
    }


def build_adaptive_research_plan(company: str, records: list[dict[str, Any]], internet: dict[str, Any]) -> dict[str, Any]:
    base = _configured_research(company, internet)
    signals = extract_public_research_signals(records)
    company_slug = base["company_slug"]
    target_urls = list(base["target_urls"])
    target_urls.extend(signals["urls"])
    target_urls.extend(f"https://{domain}" for domain in signals["domains"] if domain not in {"crunchbase.com", "linkedin.com"})
    target_urls = dedupe_list(target_urls, int(internet.get("max_target_urls_per_company") or 10) * 3)
    lanes = [
        _lane(
            "company_identity_research",
            "Always verify company identity, website, founder/profile pages, and basic public footprint.",
            ["w3m_browser_skill", "web_browser_skill_when_profile_page_is_empty"],
            [f"{company} company website Crunchbase LinkedIn founders", f"{company} founder background company profile"],
            [url for url in target_urls if any(domain in _url_domain(url) for domain in PROFILE_DOMAINS)] or base["target_urls"][:2],
        ),
        _lane(
            "funding_research",
            "Always check funding, investor, accelerator, and press mentions.",
            ["w3m_browser_skill"],
            [f"{company} startup funding investors accelerator press", f"{company} seed round venture capital investors"],
        ),
        _lane(
            "market_map_research",
            "Map category, market context, competitors, and comparable public companies.",
            ["w3m_browser_skill"],
            [f"{company} competitors market size comparable companies", f"{company} industry report public company comparables market multiple"],
        ),
        _lane(
            "traction_research",
            "Verify public customer, revenue, partnership, launch, and product traction claims.",
            ["w3m_browser_skill"],
            [f"{company} customers pilots revenue partnerships product launch", f"{company} customer case study ARR retention growth"],
        ),
    ]
    if signals["github_urls"] or "github" in signals["technical_terms"] or "open source" in signals["technical_terms"]:
        lanes.append(
            _lane(
                "github_research",
                "GitHub or open-source signal was present in the packet; inspect public repo/org activity and technical credibility.",
                ["w3m_browser_skill.direct_page", "web_browser_skill_when_page_is_empty"],
                [f"{company} GitHub repository open source stars forks issues releases"],
                signals["github_urls"],
            )
        )
    if signals["docs_urls"] or signals["package_urls"] or signals["app_store_urls"] or signals["technical_terms"]:
        lanes.append(
            _lane(
                "technical_product_research",
                "Technical/product signals were present; inspect docs, package/app footprint, developer surface, and product maturity.",
                ["w3m_browser_skill.direct_page", "w3m_browser_skill.search"],
                [f"{company} API docs SDK developer documentation product", f"{company} app store package release changelog"],
                signals["docs_urls"] + signals["package_urls"] + signals["app_store_urls"],
            )
        )
    if signals["profile_urls"]:
        lanes.append(
            _lane(
                "founder_research",
                "Public profile links were present; inspect founder/company profile pages without using contact details.",
                ["w3m_browser_skill.direct_page", "web_browser_skill_when_profile_page_is_empty"],
                [f"{company} founder background public profile"],
                signals["profile_urls"],
            )
        )
    if signals["pricing_terms"]:
        lanes.append(
            _lane(
                "pricing_business_model_research",
                "Pricing or business-model terms were present; look for public pricing, packaging, and monetization evidence.",
                ["w3m_browser_skill.search"],
                [f"{company} pricing subscription business model revenue model"],
            )
        )
    if signals["regulatory_terms"]:
        lanes.append(
            _lane(
                "regulatory_risk_research",
                "Regulatory or security claims were present; inspect public compliance and risk context.",
                ["w3m_browser_skill.search"],
                [f"{company} security compliance regulatory privacy SOC 2 GDPR"],
            )
        )
    if signals["ip_terms"]:
        lanes.append(
            _lane(
                "data_ip_defensibility_research",
                "Data, IP, model, or patent terms were present; inspect defensibility and asset evidence.",
                ["w3m_browser_skill.search"],
                [f"{company} patent proprietary dataset model defensibility"],
            )
        )

    stage_queries = {
        "company_identity_researcher": [],
        "funding_researcher": [],
        "market_comp_researcher": [],
        "traction_verifier": [],
        "rendered_page_researcher": [],
    }
    stage_target_urls = {
        "company_identity_researcher": [],
        "funding_researcher": [],
        "market_comp_researcher": [],
        "traction_verifier": [],
        "rendered_page_researcher": [],
    }
    lane_stage = {
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
        stage = lane_stage.get(lane["lane_id"])
        if stage:
            stage_queries[stage].extend(lane["queries"])
            stage_target_urls[stage].extend(lane["target_urls"])
    rendered_urls = [
        url for url in target_urls
        if any(domain in _url_domain(url) for domain in JS_HEAVY_DOMAINS)
    ]
    if rendered_urls:
        stage_queries["rendered_page_researcher"].append(f"{company} rendered public profile pages")
    else:
        stage_queries["rendered_page_researcher"].append(f"{company} Crunchbase organization profile rendered page")
    max_queries = int(internet.get("max_queries") or 20)
    for stage, queries in list(stage_queries.items()):
        stage_queries[stage] = dedupe_list(queries or base["queries"], max_queries)
        stage_target_urls[stage] = dedupe_list(stage_target_urls[stage], int(internet.get("max_target_urls_per_company") or 10) * 2)

    return {
        **base,
        "adaptive": True,
        "signals": signals,
        "lanes": lanes,
        "stage_queries": stage_queries,
        "stage_target_urls": stage_target_urls,
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


def method_result(
    *,
    method_id: str,
    scorer_id: str,
    memory_hook: str,
    status: str,
    score: float | int | None,
    inputs_used: list[str],
    formula_or_weighting: Any,
    assumptions: list[str],
    source_refs: list[str],
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
    missing_evidence: list[str] | None = None,
    evidence_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_missing = missing_evidence if missing_evidence is not None else ([] if status == "scored" else list(warnings or ["Evidence was insufficient to score this method."]))
    resolved_status_reason = method_status_reason(
        method_id=method_id,
        status=status,
        score=score,
        inputs_used=inputs_used,
        source_refs=source_refs,
        missing_evidence=resolved_missing,
        assumptions=assumptions,
    )
    resolved_evidence_summary = evidence_summary or {
        "evidence_ref_count": len(source_refs),
        "status_reason": resolved_status_reason,
        "assumption_count": len(assumptions),
        "assumptions": assumptions,
        "assumption_evidence_gaps": resolved_missing,
        "method_purpose": method_guidance(method_id)["purpose"],
        "judge_rubric": JUDGE_RUBRIC,
    }
    resolved_evidence_summary.setdefault("status_reason", resolved_status_reason)
    resolved_evidence_summary.setdefault("method_purpose", method_guidance(method_id)["purpose"])
    resolved_evidence_summary.setdefault("judge_rubric", JUDGE_RUBRIC)
    return {
        "method_id": method_id,
        "scorer_id": scorer_id,
        "memory_hook": memory_hook,
        "status": status,
        "score": round(score, 2) if isinstance(score, (int, float)) else None,
        "inputs_used": inputs_used,
        "formula_or_weighting": formula_or_weighting,
        "assumptions": assumptions,
        "source_refs": source_refs,
        "evidence_refs": source_refs,
        "evidence_summary": resolved_evidence_summary,
        "missing_evidence": resolved_missing,
        "warnings": warnings or [],
        "details": details or {},
    }


def score_berkus(facts: dict[str, Any]) -> dict[str, Any]:
    buckets = {
        "sound_idea": facts["market_facts"]["score"],
        "prototype": facts["product_facts"]["score"],
        "quality_management_team": facts["team_facts"]["score"],
        "strategic_relationships": facts["relationship_facts"]["score"],
        "product_rollout_or_sales": facts["traction_facts"]["score"],
    }
    status = "scored" if any(buckets.values()) else "insufficient_evidence"
    return method_result(
        method_id="berkus_method",
        scorer_id="berkus_scorer",
        memory_hook="5 buckets",
        status=status,
        score=sum(buckets.values()) / len(buckets) if status == "scored" else None,
        inputs_used=list(buckets),
        formula_or_weighting="average(sound_idea, prototype, team, strategic_relationships, rollout_or_sales)",
        assumptions=["Bucket scores are 0-100 evidence-strength indicators, not a valuation."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["market_facts"]["public_source_refs"][:5],
        details={"buckets": buckets},
    )


def score_scorecard(facts: dict[str, Any]) -> dict[str, Any]:
    weights = {
        "team": 0.30,
        "market": 0.25,
        "product": 0.15,
        "traction": 0.15,
        "competition": 0.10,
        "financing_need": 0.05,
    }
    factors = {
        "team": facts["team_facts"]["score"],
        "market": facts["market_facts"]["score"],
        "product": facts["product_facts"]["score"],
        "traction": facts["traction_facts"]["score"],
        "competition": max(0, 100 - facts["risk_facts"]["score"]),
        "financing_need": 60 if facts["financial_facts"]["local_monetary_values"] else 25,
    }
    substantive_inputs = [key for key in ("team", "market", "product", "traction") if factors[key] > 0]
    if facts["financial_facts"]["local_monetary_values"]:
        substantive_inputs.append("financing_need")
    status = "scored" if substantive_inputs else "insufficient_evidence"
    return method_result(
        method_id="scorecard_bill_payne_method",
        scorer_id="scorecard_bill_payne_scorer",
        memory_hook="Compare to the average startup",
        status=status,
        score=sum(factors[key] * weight for key, weight in weights.items()) if status == "scored" else None,
        inputs_used=list(factors),
        formula_or_weighting=weights,
        assumptions=["Weights are default early-stage screening weights and should be calibrated by fund strategy."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["market_facts"]["public_source_refs"][:5],
        warnings=["Competition and financing-need defaults are not sufficient evidence by themselves."] if status == "scored" else ["No substantive Scorecard evidence found."],
        details={
            "factors": factors,
            "substantive_inputs": substantive_inputs,
            "non_substantive_default_inputs": ["competition"] + ([] if facts["financial_facts"]["local_monetary_values"] else ["financing_need"]),
        },
    )


def score_risk_factor_summation(facts: dict[str, Any]) -> dict[str, Any]:
    risk_factors = [
        "management",
        "stage",
        "legislation",
        "manufacturing",
        "sales",
        "funding",
        "competition",
        "technology",
        "litigation",
        "international",
        "reputation",
        "exit",
    ]
    text_terms = set(facts["risk_facts"]["warning_terms"])
    adjustments = {
        factor: {
            "adjustment": -1 if factor in text_terms else 0,
            "status": "scored" if factor in text_terms else "insufficient_evidence",
        }
        for factor in risk_factors
    }
    status = "scored" if facts["risk_facts"]["score"] else "insufficient_evidence"
    return method_result(
        method_id="risk_factor_summation_method",
        scorer_id="risk_factor_summation_scorer",
        memory_hook="12-risk checklist",
        status=status,
        score=max(0, 100 - facts["risk_facts"]["score"]) if status == "scored" else None,
        inputs_used=risk_factors,
        formula_or_weighting="100 - keyword_risk_score; adjustment table records observed risk factors",
        assumptions=["Risk adjustments are directional diligence prompts, not price adjustments."],
        source_refs=facts["team_facts"]["evidence_refs"],
        warnings=["Several risk checklist factors lack explicit evidence."] if status == "scored" else ["No explicit risk evidence found."],
        details={"risk_adjustments": adjustments},
    )


def score_venture_capital_method(facts: dict[str, Any]) -> dict[str, Any]:
    largest_value = facts["financial_facts"]["largest_relevant_value"]
    assumed_exit_value = largest_value * 8 if largest_value else None
    status = "scored" if assumed_exit_value else "insufficient_evidence"
    score = min(100, facts["traction_facts"]["score"] * 0.6 + facts["market_facts"]["score"] * 0.4) if status == "scored" else None
    return method_result(
        method_id="venture_capital_method",
        scorer_id="venture_capital_method_scorer",
        memory_hook="Work backward from exit",
        status=status,
        score=score,
        inputs_used=["largest_relevant_monetary_value", "traction_score", "market_score"],
        formula_or_weighting={"assumed_exit_value": "largest_relevant_value * 8", "score": "0.6 * traction + 0.4 * market"},
        assumptions=["Uses the largest extracted local/public/tool monetary figure as a rough proxy only when available.", "Required return multiple defaults to 10x."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["comparable_candidates"]["public_source_refs"][:5],
        warnings=[] if status == "scored" else ["No monetary value found for exit-back math."],
        details={"assumed_exit_value": assumed_exit_value, "required_return_multiple": 10, "monetary_value_source": "local_or_public_or_financial_tool"},
        missing_evidence=[] if status == "scored" else ["No local, public, or financial-tool monetary value was available for exit-back math."],
    )


def score_first_chicago(facts: dict[str, Any]) -> dict[str, Any]:
    has_values = bool(facts["financial_facts"]["local_monetary_values"] or facts["financial_facts"]["public_monetary_values"] or facts["financial_facts"]["tool_monetary_values"])
    status = "scored" if has_values and facts["traction_facts"]["score"] >= 15 else "insufficient_evidence"
    cases = {
        "bear": {"probability": 0.35, "score": max(0, facts["traction_facts"]["score"] - 25)},
        "base": {"probability": 0.45, "score": round((facts["traction_facts"]["score"] + facts["market_facts"]["score"]) / 2, 2)},
        "bull": {"probability": 0.20, "score": min(100, max(facts["traction_facts"]["score"], facts["market_facts"]["score"]) + 20)},
    }
    weighted = sum(case["probability"] * case["score"] for case in cases.values()) if status == "scored" else None
    return method_result(
        method_id="first_chicago_method",
        scorer_id="first_chicago_scorer",
        memory_hook="Bear/base/bull cases",
        status=status,
        score=weighted,
        inputs_used=["traction_score", "market_score", "local_monetary_values"],
        formula_or_weighting="0.35 * bear + 0.45 * base + 0.20 * bull",
        assumptions=["Scenario probabilities are defaults and should be adjusted by investment committee policy."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["market_facts"]["public_source_refs"][:5],
        warnings=[] if status == "scored" else ["Scenario math needs both traction and monetary evidence."],
        details={"cases": cases},
        missing_evidence=[] if status == "scored" else ["First Chicago needs monetary evidence plus traction evidence before scenario math is useful."],
    )


def score_comparables(facts: dict[str, Any]) -> dict[str, Any]:
    source_count = facts["comparable_candidates"]["source_count"]
    status = "scored" if source_count else "insufficient_evidence"
    return method_result(
        method_id="comparables_market_multiple_method",
        scorer_id="comparables_market_multiple_scorer",
        memory_hook="What are similar companies worth?",
        status=status,
        score=(facts["market_facts"]["score"] + facts["traction_facts"]["score"]) / 2 if status == "scored" else None,
        inputs_used=["market_score", "traction_score", "public_source_count", "comparable_domains"],
        formula_or_weighting="average(market_score, traction_score) when public comparable evidence exists",
        assumptions=["Public comparable snippets are screening evidence; no private transaction database is assumed."],
        source_refs=facts["comparable_candidates"]["public_source_refs"],
        warnings=[] if status == "scored" else ["No substantive public comparable evidence found."],
        details={"source_count": source_count, "domains": facts["comparable_candidates"]["domains"][:12], "financial_tool_outputs": facts["financial_facts"]["financial_tool_outputs"]},
        missing_evidence=[] if status == "scored" else ["No substantive public comparable source or deterministic financial-tool comparable was available."],
    )


def score_cost_to_duplicate(facts: dict[str, Any]) -> dict[str, Any]:
    status = evidence_status(facts["ip_asset_facts"]["score"])
    return method_result(
        method_id="cost_to_duplicate_method",
        scorer_id="cost_to_duplicate_scorer",
        memory_hook="What would it cost to rebuild?",
        status=status,
        score=facts["ip_asset_facts"]["score"] if status == "scored" else None,
        inputs_used=["ip_asset_score", "product_score", "asset_keywords"],
        formula_or_weighting="asset keyword evidence score across built, patent, R&D, dataset, hardware, model, and infrastructure terms",
        assumptions=["Cost-to-duplicate is a floor proxy and misses upside."],
        source_refs=facts["team_facts"]["evidence_refs"],
        warnings=[] if status == "scored" else ["No rebuild-cost asset evidence found."],
        details={"evidence_terms": facts["ip_asset_facts"]["keywords"]},
    )


def score_company_methods(facts: dict[str, Any], max_workers: int = 1) -> dict[str, Any]:
    scorers = [
        score_berkus,
        score_scorecard,
        score_risk_factor_summation,
        score_venture_capital_method,
        score_first_chicago,
        score_comparables,
        score_cost_to_duplicate,
    ]
    worker_count = bounded_int(max_workers, default=min(7, len(scorers)), maximum=len(scorers))
    if worker_count <= 1:
        results = [scorer(facts) for scorer in scorers]
    else:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="vc-scorer") as executor:
            futures = {executor.submit(scorer, facts): scorer.__name__ for scorer in scorers}
            results = [future.result() for future in as_completed(futures)]
    by_method = {result["method_id"]: result for result in results}
    return {method_id: by_method[method_id] for method_id in METHOD_IDS}


def audit_method_scores(methods: dict[str, dict[str, Any]], facts: dict[str, Any]) -> dict[str, Any]:
    findings = []
    for method_id in METHOD_IDS:
        method = methods.get(method_id)
        if not method:
            findings.append({"severity": "error", "method_id": method_id, "message": "Method score missing."})
            continue
        if method["status"] == "scored" and method["score"] is None:
            findings.append({"severity": "error", "method_id": method_id, "message": "Scored method has no numeric score."})
        if method["status"] == "insufficient_evidence" and method["score"] is not None:
            findings.append({"severity": "warning", "method_id": method_id, "message": "Insufficient-evidence method should not carry a numeric score."})
        for field in ("inputs_used", "formula_or_weighting", "assumptions", "source_refs", "evidence_refs", "evidence_summary", "missing_evidence", "warnings"):
            if field not in method:
                findings.append({"severity": "error", "method_id": method_id, "message": f"Missing {field}."})
        if method_id == "scorecard_bill_payne_method" and method["status"] == "scored" and method.get("details", {}).get("non_substantive_default_inputs"):
            findings.append({"severity": "warning", "method_id": method_id, "message": "Scorecard includes non-substantive default inputs; substantive evidence gates controlled scoring status."})
    unsupported = []
    if facts["financial_facts"]["largest_local_value"] and not facts["traction_facts"]["score"]:
        unsupported.append("Financial value found without traction terms; review whether value is relevant.")
    return {
        "company_name": facts["company_name"],
        "company_slug": facts["company_slug"],
        "status": "checked_with_warnings" if findings or unsupported else "checked",
        "findings": findings,
        "unsupported_assumption_warnings": unsupported,
        "checked_at": utc_now_iso(),
    }


def build_company_analysis(company: str, records: list[dict[str, Any]], research_ledger: dict[str, list[dict[str, Any]]], scoring_workers: int = 1) -> dict[str, Any]:
    sources = [source for stage_sources in research_ledger.values() for source in stage_sources]
    facts = build_fact_table(company, records, sources)
    methods = score_company_methods(facts, max_workers=scoring_workers)
    audit = audit_method_scores(methods, facts)
    scored = [item["score"] for item in methods.values() if isinstance(item.get("score"), (int, float))]
    missing_methods = [method_id for method_id, method in methods.items() if method["status"] == "insufficient_evidence"]
    substantive_sources = [source for source in sources if is_substantive_public_source(source)]
    composite_score = round(sum(scored) / len(scored), 2) if scored else None
    return {
        "company_name": company,
        "company_slug": slugify(company),
        "composite_score": composite_score,
        "method_count": len(methods),
        "methods": methods,
        "fact_table": facts,
        "audit": audit,
        "evidence_summary": {
            "document_count": len(records),
            "source_count": len(sources),
            "substantive_source_count": len(substantive_sources),
            "financial_tool_source_count": len([source for source in sources if source.get("skill") == "financial_public_data_tool"]),
            "missing_methods": missing_methods,
            "composite_score_evidence": {
                "status": "scored" if scored else "insufficient_evidence",
                "scored_method_count": len(scored),
                "method_ids": [method_id for method_id, method in methods.items() if isinstance(method.get("score"), (int, float))],
                "reason": "Composite is the average of scored method outputs." if scored else "No method had enough evidence for a numeric score.",
            },
        },
        "result_evidence": {
            "composite_score": {
                "value": composite_score,
                "why": "Average of method scores with sufficient evidence." if scored else "No scored methods were available.",
                "evidence_refs": sorted({ref for method in methods.values() for ref in method.get("evidence_refs", []) if ref})[:20],
                "missing_evidence": missing_methods,
            },
            "research": {
                "source_count": len(sources),
                "substantive_source_count": len(substantive_sources),
                "budget_or_source_warnings": [source.get("warning") for source in sources if source.get("warning")],
            },
        },
        "decision_policy": "report_only_user_decides",
    }


def score_company(company: str, records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return build_company_analysis(company, records, {"legacy_research": sources})


def flattened_sources(research_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [source for stage_sources in research_ledger.values() for source in stage_sources]


def warnings_for_company(analysis: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for source in sources:
        if source.get("warning") or source.get("status") in WARNING_SOURCE_STATUSES:
            warnings.append({
                "kind": "research",
                "status": source.get("status"),
                "source": source.get("url"),
                "message": source.get("warning") or source.get("snippet"),
            })
    for method in analysis["methods"].values():
        for warning in method.get("warnings") or []:
            warnings.append({"kind": "method", "method_id": method["method_id"], "message": warning})
    for finding in analysis["audit"].get("findings") or []:
        warnings.append({"kind": "audit", **finding})
    return warnings


def research_gap_followups(analysis: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
    followups = []
    plan = analysis.get("research_plan") or {}
    for lane in plan.get("lanes") or []:
        followups.append(f"Review {lane.get('lane_id')}: {lane.get('reason')}")
    reconciliation = analysis.get("research_reconciliation") or {}
    for missing in reconciliation.get("missing_public_evidence") or []:
        topic = missing.get("topic") or "public evidence"
        followups.append(f"Find public confirmation for local {topic} claims.")
    for method_id in analysis.get("evidence_summary", {}).get("missing_methods", []):
        followups.append(f"Add stronger evidence for {method_id.replace('_', ' ')} before relying on its score.")
    for source in sources:
        if source.get("status") in WARNING_SOURCE_STATUSES:
            followups.append(f"Revisit {source.get('verification_target')}: {source.get('warning') or source.get('snippet')}")
    return dedupe_list(followups, 12)


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
        f"{company} startup revenue customers pilots partnerships",
        f"{company} founder background LinkedIn company profile",
        f"{company} startup investors accelerator seed round",
        f"{company} market size industry report competitors",
        f"{company} SEC public company comparables market multiple",
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


def infer_source_quality_label(status: str, skill: str, verification_target: str, url: str, snippet: str) -> str:
    lowered_status = str(status or "").lower()
    lowered_skill = str(skill or "").lower()
    lowered_target = str(verification_target or "").lower()
    lowered_url = str(url or "").lower()
    lowered_snippet = str(snippet or "").lower()
    if lowered_status in {"blocked", "failed", "skill_unavailable", "budget_exhausted", "disabled"}:
        return "blocked"
    if lowered_status in {"planned", "configured_reference", "warning"}:
        return "thin_signal"
    if "financial_public_data_tool" in lowered_skill or any(domain in lowered_url for domain in ("sec.gov", "bls.gov", "sba.gov")):
        return "market_context"
    if "github.com" in lowered_url or any(term in lowered_target for term in ("github", "technical", "product")):
        return "technical_signal"
    if any(term in lowered_snippet for term in ("conflict", "contradict", "unconfirmed")):
        return "public_conflict"
    if lowered_url.startswith(("http://", "https://")) and lowered_status in {"ok", "completed"}:
        return "public_confirmation"
    return "thin_signal"


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
    source_quality_label: str | None = None,
) -> dict[str, Any]:
    snippet_limit = 10000 if skill == "financial_public_data_tool" else 1000
    quality = source_quality_label or infer_source_quality_label(status, skill, verification_target, url, snippet)
    return {
        "company": company,
        "query": query,
        "url": url,
        "title": title or url.split("//", 1)[-1].split("/", 1)[0],
        "snippet": snippet[:snippet_limit],
        "status": status,
        "skill": skill,
        "verification_target": verification_target,
        "source_quality_label": quality if quality in SOURCE_QUALITY_LABELS else "thin_signal",
        "warning": warning,
        "retrieved_at": utc_now_iso(),
    }


def _budget_exhausted_source(company: str, query: str, skill: str, verification_target: str, action_type: str) -> dict[str, Any]:
    return _source_record(
        company=company,
        query=query,
        url="action_budget",
        title="Action budget exhausted",
        snippet=f"Skipped {action_type} because the VC Assistant action budget was exhausted.",
        status="budget_exhausted",
        skill=skill,
        verification_target=verification_target,
        warning="Action budget exhausted before this evidence source could be collected.",
    )


def agentic_research_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("agentic_research") if isinstance(config.get("agentic_research"), dict) else {}
    if quick_test_mode_enabled(config):
        return {
            "enabled": False,
            "agent_ids": [str(item) for item in (raw.get("agent_ids") or DEFAULT_AGENTIC_RESEARCH_AGENT_IDS)],
            "max_iterations_per_agent": 1,
            "max_tool_calls_per_agent": 0,
            "allowed_tools": [str(item) for item in (raw.get("allowed_tools") or DEFAULT_AGENTIC_RESEARCH_TOOLS)],
        }
    return {
        "enabled": bool(raw.get("enabled", True)),
        "agent_ids": [str(item) for item in (raw.get("agent_ids") or DEFAULT_AGENTIC_RESEARCH_AGENT_IDS)],
        "max_iterations_per_agent": bounded_int(raw.get("max_iterations_per_agent"), default=1, minimum=1, maximum=100),
        "max_tool_calls_per_agent": bounded_int(raw.get("max_tool_calls_per_agent"), default=2, minimum=0, maximum=500),
        "allowed_tools": [str(item) for item in (raw.get("allowed_tools") or DEFAULT_AGENTIC_RESEARCH_TOOLS)],
    }


def actor_review_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("actor_review") if isinstance(config.get("actor_review"), dict) else {}
    selected = raw.get("llm_actor_ids") if isinstance(raw.get("llm_actor_ids"), list) else DEFAULT_ACTOR_REVIEW_LLM_ACTOR_IDS
    return {
        "llm_actor_ids": [str(item) for item in selected],
        "max_context_chars": bounded_int(raw.get("max_context_chars"), default=12000, minimum=2000, maximum=50000),
    }


def _agent_stage_enabled(agentic: dict[str, Any], stage: str) -> bool:
    return bool(agentic.get("enabled")) and stage in set(agentic.get("agent_ids") or [])


def _agent_tool_source(
    *,
    company: str,
    agent_id: str,
    query: str,
    status: str,
    message: str,
    tool_call_id: str = "",
) -> dict[str, Any]:
    record = _source_record(
        company=company,
        query=query,
        url="agent_tool_loop",
        title=f"{agent_id} tool loop",
        snippet=message,
        status=status,
        skill="llm_tool_agent",
        verification_target=agent_id,
        warning=message if status in {"agent_tool_loop_failed", "agent_invalid_tool_call", "blocked"} else "",
        source_quality_label="blocked" if status in {"agent_tool_loop_failed", "agent_invalid_tool_call", "blocked"} else "thin_signal",
    )
    record["agent_id"] = agent_id
    record["tool_call_id"] = tool_call_id
    record["tool_decision_source"] = "llm_agent"
    return record


def _annotate_agent_sources(sources: list[dict[str, Any]], start_index: int, *, agent_id: str, tool_call_id: str) -> None:
    for source in sources[start_index:]:
        source["agent_id"] = agent_id
        source["tool_call_id"] = tool_call_id
        source["tool_decision_source"] = "llm_agent"


def _blocked_tool_text(value: str, internet: dict[str, Any]) -> str:
    lowered = value.lower()
    blocked = [
        "raw document text",
        "confidential",
        "private financial",
        "customer names",
        "founder contact",
        "phone",
        "email",
    ]
    blocked.extend(str(item).replace("_", " ").lower() for item in (internet.get("blocked_inputs") or []))
    for marker in blocked:
        if marker and marker in lowered:
            return marker
    return ""


def _validate_agent_tool_call(tool_call: dict[str, Any], *, allowed_tools: set[str], internet: dict[str, Any]) -> str:
    tool = str(tool_call.get("tool") or "")
    if tool not in allowed_tools:
        return f"Tool '{tool}' is not allowed for this agent."
    if tool == "finish":
        return ""
    query = str(tool_call.get("query") or "")
    url = str(tool_call.get("url") or "")
    if tool == "browser_search" and not query.strip():
        return "browser_search requires a query."
    if tool in {"browser_page", "rendered_browser_page"} and not url.startswith(("http://", "https://")):
        return f"{tool} requires an http(s) url."
    blocked = _blocked_tool_text(f"{query} {url}", internet)
    if blocked:
        return f"Tool call includes blocked private/confidential input marker: {blocked}."
    return ""


def _agent_observation_from_sources(sources: list[dict[str, Any]], start_index: int) -> dict[str, Any]:
    added = sources[start_index:]
    return {
        "source_count": len(added),
        "statuses": sorted({str(source.get("status") or "") for source in added if source.get("status")}),
        "urls": [str(source.get("url") or "") for source in added[:5]],
        "snippets": [str(source.get("snippet") or "")[:240] for source in added[:3]],
    }


def _execute_agent_tool_call(
    *,
    sources: list[dict[str, Any]],
    company: str,
    stage: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    action_budget: ActionBudget | None,
    tool_call: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    tool = str(tool_call.get("tool") or "")
    if tool == "finish":
        return {"status": "finished", "source_count": 0, "stop_reason": str(tool_call.get("reason") or "finish")}
    start_index = len(sources)
    tool_plan = dict(plan)
    query = str(tool_call.get("query") or (plan.get("queries") or [""])[0])
    url = str(tool_call.get("url") or "")
    tool_plan["queries"] = [query]
    if url:
        tool_plan["target_urls"] = [url]
    if tool == "browser_search":
        call_with_supported_kwargs(_append_w3m_research, sources=sources, company=company, plan=tool_plan, internet=internet, run_dir=run_dir, verification_target=stage, action_budget=action_budget)
    elif tool == "browser_page":
        call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=tool_plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
    elif tool == "rendered_browser_page":
        rendered_internet = dict(internet)
        rendered = dict(rendered_internet.get("rendered_browser") or {})
        rendered["enabled"] = True
        rendered_internet["rendered_browser"] = rendered
        call_with_supported_kwargs(_append_rendered_browser_research, sources=sources, company=company, plan=tool_plan, internet=rendered_internet, action_budget=action_budget)
    _annotate_agent_sources(sources, start_index, agent_id=stage, tool_call_id=tool_call_id)
    return {"status": "executed", **_agent_observation_from_sources(sources, start_index)}


def _default_agent_tool_response(stage: str, plan: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    if observations:
        return {
            "thought_summary": "Existing observations are sufficient for this bounded pass.",
            "tool_calls": [{"tool": "finish", "reason": "observations_collected"}],
            "stop_reason": "observations_collected",
            "evidence_gaps": [],
        }
    query = (plan.get("stage_queries") or {}).get(stage, []) or plan.get("queries") or []
    urls = (plan.get("stage_target_urls") or {}).get(stage, []) or []
    if stage == "rendered_page_researcher":
        urls = plan.get("rendered_target_urls") or urls
    if urls and stage in {"company_identity_researcher", "market_comp_researcher", "traction_verifier"}:
        return {
            "thought_summary": "Inspect a known public URL selected by the adaptive plan.",
            "tool_calls": [{"tool": "browser_page", "url": urls[0], "query": query[0] if query else ""}],
            "stop_reason": "",
            "evidence_gaps": [],
        }
    if urls and stage == "rendered_page_researcher":
        return {
            "thought_summary": "Inspect a rendered public profile URL selected by the adaptive plan.",
            "tool_calls": [{"tool": "rendered_browser_page", "url": urls[0], "query": query[0] if query else ""}],
            "stop_reason": "",
            "evidence_gaps": [],
        }
    return {
        "thought_summary": "Run one broad public search selected by the adaptive plan.",
        "tool_calls": [{"tool": "browser_search", "query": query[0] if query else f"{plan.get('company', '')} startup public evidence"}],
        "stop_reason": "",
        "evidence_gaps": [],
    }


def research_prompt_spec(agent_id: str) -> dict[str, Any]:
    return dict(RESEARCH_AGENT_PROMPT_SPECS.get(agent_id) or RESEARCH_AGENT_PROMPT_SPECS["research_planner"])


def build_research_agent_prompt(
    *,
    company: str,
    stage: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    allowed_tools: set[str],
    remaining_tool_calls: int,
    rag_context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
    observations: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    spec = research_prompt_spec(stage)
    system_prompt = (
        f"You are {stage}, a specialist VC diligence research actor. "
        f"Mission: {spec['mission']} Return strict JSON only. "
        "Use RAG refs when supplied. Never issue pass/watch/reject/buy/sell/invest recommendations."
    )
    return system_prompt, {
        "task": "Choose the next bounded public research tool call for this specialist VC diligence stage.",
        "company": company,
        "agent_id": stage,
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
            "stage_queries": (plan.get("stage_queries") or {}).get(stage, []),
            "stage_target_urls": (plan.get("stage_target_urls") or {}).get(stage, []),
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


def run_agentic_research_stage(
    *,
    company: str,
    stage: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    action_budget: ActionBudget | None,
    llm: Any,
    agentic: dict[str, Any],
    trace: list[dict[str, Any]] | None,
    knowledge_rag: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    queries = (plan.get("stage_queries") or {}).get(stage, []) or plan.get("queries") or []
    sources = [_research_stage_plan_record(company, stage, item, plan) for item in queries]
    allowed_tools = set(agentic.get("allowed_tools") or DEFAULT_AGENTIC_RESEARCH_TOOLS)
    max_iterations = int(agentic.get("max_iterations_per_agent") or 20)
    max_tool_calls = int(agentic.get("max_tool_calls_per_agent") or 50)
    stage_operation_id = f"agentic-research-{slugify(stage)}-{uuid.uuid4().hex[:8]}"
    stage_started = time.monotonic()
    append_observation_record(
        run_dir,
        "observability_operation_started",
        {
            "operation_id": stage_operation_id,
            "phase": "agentic_research",
            "operation": stage,
            "status": "started",
            "company": company,
            "agent_id": stage,
            "max_iterations": max_iterations,
            "max_tool_calls": max_tool_calls,
        },
    )
    rag_query = " ".join(
        item
        for item in [
            company,
            stage,
            " ".join(queries[:3]),
            " ".join(str(lane.get("lane_id") or "") for lane in plan.get("lanes", [])[:8] if isinstance(lane, dict)),
        ]
        if item
    )
    rag_context = retrieve_knowledge_rag_context(knowledge_rag=knowledge_rag, query=rag_query, stage=stage, company=company, run_dir=run_dir)
    require_ready_rag(knowledge_rag, stage=stage, company=company, context=rag_context, min_citations=1, run_dir=run_dir)
    observations: list[dict[str, Any]] = []
    executed_tool_calls = 0
    trace_record = {
        "agent_id": stage,
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
        fallback = _default_agent_tool_response(stage, plan, observations)
        system_prompt, prompt = build_research_agent_prompt(
            company=company,
            stage=stage,
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
            sources.append(_agent_tool_source(company=company, agent_id=stage, query=queries[0] if queries else "", status="agent_tool_loop_failed", message=message))
            trace_record["iterations"].append({"iteration": iteration, "status": "failed", "error": str(exc)})
            trace_record["stop_reason"] = "agent_tool_loop_failed"
            break
        if isinstance(decision, dict) and decision.get("provider") == "budget_exhausted":
            message = "Agent tool loop stopped because the action budget was exhausted before the LLM could choose tools."
            sources.append(_agent_tool_source(company=company, agent_id=stage, query=queries[0] if queries else "", status="budget_exhausted", message=message))
            trace_record["iterations"].append({"iteration": iteration, "status": "budget_exhausted"})
            trace_record["stop_reason"] = "budget_exhausted"
            break
        if not isinstance(decision, dict):
            message = "Agent returned non-object JSON for tool decision."
            sources.append(_agent_tool_source(company=company, agent_id=stage, query=queries[0] if queries else "", status="agent_invalid_tool_call", message=message))
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
            validate_llm_rag_refs(decision, knowledge_rag=knowledge_rag, stage=stage, company=company)
        except Exception as exc:
            sources.append(_agent_tool_source(company=company, agent_id=stage, query=queries[0] if queries else "", status="agent_invalid_tool_call", message=str(exc)))
            trace_record["iterations"].append({"iteration": iteration, "status": "invalid_rag_refs", "error": str(exc)})
            trace_record["stop_reason"] = "required_rag_refs_missing"
            trace_record["budget_end"] = action_budget.summary(include_actions=False) if action_budget else {}
            if trace is not None:
                trace.append(trace_record)
            append_observation_record(
                run_dir,
                "observability_operation_failed",
                {
                    "operation_id": stage_operation_id,
                    "phase": "agentic_research",
                    "operation": stage,
                    "status": "failed",
                    "company": company,
                    "agent_id": stage,
                    "error": str(exc),
                    "elapsed_ms": round((time.monotonic() - stage_started) * 1000, 2),
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
            sources.append(_agent_tool_source(company=company, agent_id=stage, query=queries[0] if queries else "", status="agent_invalid_tool_call", message=message))
            trace_record["validation_failures"].append({"iteration": iteration, "message": message})
            iteration_record["stop_reason"] = "agent_invalid_tool_call"
            trace_record["iterations"].append(iteration_record)
            trace_record["stop_reason"] = "agent_invalid_tool_call"
            break
        finished = False
        for raw_call in tool_calls:
            if executed_tool_calls >= max_tool_calls:
                trace_record["stop_reason"] = "max_tool_calls_reached"
                break
            tool_call = raw_call if isinstance(raw_call, dict) else {"tool": ""}
            tool_call_id = f"{stage}-{iteration}-{len(iteration_record['executed_tool_calls']) + 1}"
            validation_error = _validate_agent_tool_call(tool_call, allowed_tools=allowed_tools, internet=internet)
            if validation_error:
                sources.append(_agent_tool_source(company=company, agent_id=stage, query=str(tool_call.get("query") or ""), status="agent_invalid_tool_call", message=validation_error, tool_call_id=tool_call_id))
                append_event(run_dir, "tool_call_failed", {"tool": tool_call.get("tool"), "agent_id": stage, "tool_call_id": tool_call_id, "company": company, "error": validation_error}) if run_dir else None
                trace_record["validation_failures"].append({"iteration": iteration, "tool_call_id": tool_call_id, "message": validation_error, "tool_call": tool_call})
                iteration_record["executed_tool_calls"].append({"tool_call_id": tool_call_id, "status": "invalid", "message": validation_error})
                continue
            if str(tool_call.get("tool") or "") == "finish":
                finished = True
                iteration_record["executed_tool_calls"].append({"tool_call_id": tool_call_id, "tool": "finish", "status": "finished", "reason": str(tool_call.get("reason") or decision.get("stop_reason") or "finish")})
                continue
            append_event(run_dir, "tool_call_started", {"tool": tool_call.get("tool"), "agent_id": stage, "tool_call_id": tool_call_id, "company": company}) if run_dir else None
            with observed_operation(
                run_dir,
                phase="public_tool_call",
                operation=str(tool_call.get("tool") or "unknown_tool"),
                company=company,
                agent_id=stage,
                tool_call_id=tool_call_id,
                query_hash=stable_text_hash(tool_call.get("query") or ""),
                query_chars=len(str(tool_call.get("query") or "")),
                url_host=host_from_url(str(tool_call.get("url") or "")) if tool_call.get("url") else "",
            ) as op:
                result = _execute_agent_tool_call(sources=sources, company=company, stage=stage, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget, tool_call=tool_call, tool_call_id=tool_call_id)
                op.close("completed" if result.get("status") in {"executed", "finished"} else "failed", tool_status=result.get("status"), source_count=result.get("source_count"))
            executed_tool_calls += 1
            observation = {"tool_call_id": tool_call_id, "tool": tool_call.get("tool"), "result": result}
            observations.append(observation)
            iteration_record["executed_tool_calls"].append({"tool_call_id": tool_call_id, "tool": tool_call.get("tool"), "status": result.get("status")})
            iteration_record["observations"].append(observation)
            event_type = "tool_call_completed" if result.get("status") in {"executed", "finished"} else "tool_call_failed"
            append_event(run_dir, event_type, {"tool": tool_call.get("tool"), "agent_id": stage, "tool_call_id": tool_call_id, "company": company, "result": result}) if run_dir else None
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
            "operation_id": stage_operation_id,
            "phase": "agentic_research",
            "operation": stage,
            "status": "completed",
            "company": company,
            "agent_id": stage,
            "stop_reason": trace_record["stop_reason"],
            "tool_call_count": executed_tool_calls,
            "elapsed_ms": round((time.monotonic() - stage_started) * 1000, 2),
            "budget_end": trace_record["budget_end"],
        },
    )
    return stage, sources


def _append_w3m_research(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    verification_target: str = "search_result_or_public_source",
    action_budget: ActionBudget | None = None,
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
                verification_target=verification_target,
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
    action = action_budget.start(
        action_type="browser_search",
        stage=verification_target,
        company=company,
        tool="w3m_browser_skill.research_topic",
        metadata={"query": query, "max_sources": max_sources},
    ) if action_budget else None
    if action_budget and action is None:
        sources.append(_budget_exhausted_source(company, query, "w3m_browser_skill", verification_target, "browser_search"))
        return
    try:
        result = research_topic(query, browser_config, max_sources=max_sources, observer=observer)
    except Exception as exc:
        if action_budget:
            action_budget.complete(action, "failed", {"error": str(exc)})
        sources.append(
            _source_record(
                company=company,
                query=query,
                url="w3m_browser_skill",
                title="w3m research failed",
                snippet=str(exc),
                status="failed",
                skill="w3m_browser_skill",
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
                url=str(source.get("url") or ""),
                title=str(source.get("title") or ""),
                snippet=str(source.get("snippet") or source.get("text") or ""),
                status=str(source.get("status") or "ok"),
                skill="w3m_browser_skill",
                verification_target=verification_target,
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
    _load_w3m_browser_skill()
    if W3mBrowserConfig is None or browse_url is None:
        for url in plan["target_urls"][: int(internet.get("max_target_urls_per_company") or 2)]:
            sources.append(
                _source_record(
                    company=company,
                    query=plan["queries"][0],
                    url=url or "w3m_browser_skill",
                    title="w3m direct page skill unavailable",
                    snippet="Install mirrorneuron-w3m-browser-skill and w3m in the worker image to enable direct public page research.",
                    status="skill_unavailable",
                    skill="w3m_browser_skill",
                    verification_target="public_profile",
                    warning="mn_w3m_browser_skill direct page import failed",
                )
            )
        return
    browser_config = W3mBrowserConfig(
        timeout_seconds=int(internet.get("timeout_seconds") or 12),
        max_chars=int(internet.get("max_chars") or 6000),
    )
    observer = _research_observer(run_dir)
    for url in plan["target_urls"][: int(internet.get("max_target_urls_per_company") or 2)]:
        target = "crunchbase" if "crunchbase.com" in url else "public_profile"
        action = action_budget.start(
            action_type="browser_page",
            stage=target,
            company=company,
            tool="w3m_browser_skill.browse_url",
            metadata={"url": url},
        ) if action_budget else None
        if action_budget and action is None:
            sources.append(_budget_exhausted_source(company, plan["queries"][0], "w3m_browser_skill", target, "browser_page"))
            continue
        try:
            result = browse_url(url, browser_config, observer=observer)
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
    action_budget: ActionBudget | None = None,
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
        action = action_budget.start(
            action_type="rendered_browser_page",
            stage="rendered_page_researcher",
            company=company,
            tool="web_browser_skill.scrape_page",
            metadata={"url": url},
        ) if action_budget else None
        if action_budget and action is None:
            sources.append(_budget_exhausted_source(company, plan["queries"][0], "web_browser_skill", "rendered_public_profile", "rendered_browser_page"))
            continue
        try:
            result = scrape_page(url, browser_config)
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
    call_with_supported_kwargs(_append_w3m_research, sources=sources, company=company, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
    call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
    call_with_supported_kwargs(_append_rendered_browser_research, sources=sources, company=company, plan=plan, internet=internet, action_budget=action_budget)
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


def _research_stage_plan_record(company: str, stage: str, query: str, plan: dict[str, Any]) -> dict[str, Any]:
    selected_lanes = [
        lane["lane_id"]
        for lane in plan.get("lanes", [])
        if query in (lane.get("queries") or [])
    ]
    return _source_record(
        company=company,
        query=query,
        url="research_plan",
        title=f"{stage.replace('_', ' ').title()} Query",
        snippet=f"Verification fields: {', '.join(plan.get('verification_fields') or [])}; selected lanes: {', '.join(selected_lanes) if selected_lanes else 'baseline'}",
        status="planned",
        skill="research_planner",
        verification_target=stage,
        source_quality_label="thin_signal",
    )


def _stage_default_source_record(company: str, stage: str, query: str, url: str) -> dict[str, Any]:
    return _source_record(
        company=company,
        query=query,
        url=url,
        title=url.split("//", 1)[-1].split("/", 1)[0],
        snippet="Configured public reference for this research stage; live browser runs can replace or supplement this source.",
        status="configured_reference",
        skill="w3m_browser_skill",
        verification_target=stage,
    )


def _stage_plan_with_targets(plan: dict[str, Any], stage: str, queries: list[str]) -> dict[str, Any]:
    stage_plan = dict(plan)
    stage_plan["queries"] = [queries[0]]
    stage_urls = (plan.get("stage_target_urls") or {}).get(stage) or []
    if stage == "rendered_page_researcher":
        stage_urls = plan.get("rendered_target_urls") or stage_urls or plan.get("target_urls") or []
    stage_plan["target_urls"] = dedupe_list(stage_urls or plan.get("target_urls") or [], 30)
    return stage_plan


def _research_one_stage(company: str, stage: str, query: str | list[str], plan: dict[str, Any], internet: dict[str, Any], run_dir: Path | None, action_budget: ActionBudget | None = None) -> tuple[str, list[dict[str, Any]]]:
    queries = query if isinstance(query, list) else [query]
    sources = [_research_stage_plan_record(company, stage, item, plan) for item in queries]
    stage_plan = _stage_plan_with_targets(plan, stage, queries)

    if stage == "company_identity_researcher":
        identity_internet = dict(internet)
        identity_internet["source_url_templates"] = [
            "https://www.crunchbase.com/organization/{company_slug}",
            "https://www.linkedin.com/company/{company_slug}",
        ]
        identity_plan = _stage_plan_with_targets(plan, stage, queries)
        identity_plan["target_urls"] = dedupe_list(identity_plan.get("target_urls", []) + [
            template.format(company=company, company_slug=plan["company_slug"])
            for template in identity_internet["source_url_templates"]
        ], 30)
        for item in queries:
            identity_plan["queries"] = [item]
            call_with_supported_kwargs(_append_w3m_research, sources=sources, company=company, plan=identity_plan, internet=identity_internet, run_dir=run_dir, verification_target=stage, action_budget=action_budget)
        call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=identity_plan, internet=identity_internet, run_dir=run_dir, action_budget=action_budget)
    elif stage in {"funding_researcher", "market_comp_researcher", "traction_verifier"}:
        for item in queries:
            stage_plan["queries"] = [item]
            call_with_supported_kwargs(_append_w3m_research, sources=sources, company=company, plan=stage_plan, internet=internet, run_dir=run_dir, verification_target=stage, action_budget=action_budget)
        if stage_plan.get("target_urls"):
            call_with_supported_kwargs(_append_target_url_research, sources=sources, company=company, plan=stage_plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
        for url in list(internet.get("default_source_urls") or DEFAULT_RESEARCH_SOURCE_URLS):
            sources.append(_stage_default_source_record(company, stage, queries[0], url))
    elif stage == "rendered_page_researcher":
        call_with_supported_kwargs(_append_rendered_browser_research, sources=sources, company=company, plan=stage_plan, internet=internet, action_budget=action_budget)
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
                    verification_target=stage,
                )
            )
    return stage, sources


def research_company_by_stage(
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
        return {stage: [] for stage in RESEARCH_STAGE_IDS}
    plan = build_adaptive_research_plan(company, records or [], internet)
    agentic = agentic_research_config(config)
    staged_queries = plan["stage_queries"]
    planner_sources: list[dict[str, Any]] = []
    if llm is not None and _agent_stage_enabled(agentic, "research_planner"):
        _, planner_sources = run_agentic_research_stage(
            company=company,
            stage="research_planner",
            plan=plan,
            internet=internet,
            run_dir=run_dir,
            action_budget=action_budget,
            llm=llm,
            agentic=agentic,
            trace=agent_tool_trace,
            knowledge_rag=knowledge_rag,
        )
    worker_count = bounded_int(internet.get("max_stage_workers"), default=min(5, len(staged_queries)), maximum=len(staged_queries))
    if worker_count <= 1:
        results = [
            (
                run_agentic_research_stage(
                    company=company,
                    stage=stage,
                    plan=plan,
                    internet=internet,
                    run_dir=run_dir,
                    action_budget=action_budget,
                    llm=llm,
                    agentic=agentic,
                    trace=agent_tool_trace,
                    knowledge_rag=knowledge_rag,
                )
                if llm is not None and _agent_stage_enabled(agentic, stage)
                else _research_one_stage(company, stage, query, plan, internet, run_dir, action_budget)
            )
            for stage, query in staged_queries.items()
        ]
    else:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="vc-research") as executor:
            futures = {
                (
                    executor.submit(
                        run_agentic_research_stage,
                        company=company,
                        stage=stage,
                        plan=plan,
                        internet=internet,
                        run_dir=run_dir,
                        action_budget=action_budget,
                        llm=llm,
                        agentic=agentic,
                        trace=agent_tool_trace,
                        knowledge_rag=knowledge_rag,
                    )
                    if llm is not None and _agent_stage_enabled(agentic, stage)
                    else executor.submit(_research_one_stage, company, stage, query, plan, internet, run_dir, action_budget)
                ): stage
                for stage, query in staged_queries.items()
            }
            results = [future.result() for future in as_completed(futures)]
    by_stage = {stage: sources for stage, sources in results}
    if planner_sources:
        by_stage["company_identity_researcher"] = planner_sources + by_stage.get("company_identity_researcher", [])
    return {stage: by_stage.get(stage, []) for stage in RESEARCH_STAGE_IDS}


def append_financial_tool_research(
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
        evidence_summary = method.get("evidence_summary") or {}
        assumptions = method.get("assumptions") or []
        lines += [
            f"### {method_id.replace('_', ' ').title()}",
            f"- Status: {method['status']}",
            f"- Score: {method.get('score') if method.get('score') is not None else 'insufficient_evidence'}",
            f"- Memory hook: {method['memory_hook']}",
            f"- Why: {evidence_summary.get('status_reason', 'not recorded')}",
            f"- Evidence refs: {len(method.get('evidence_refs') or [])}",
            f"- Assumptions: {'; '.join(assumptions) if assumptions else 'none'}",
            f"- Missing evidence: {', '.join(method.get('missing_evidence') or []) if method.get('missing_evidence') else 'none'}",
        ]
    composite_evidence = (analysis.get("result_evidence") or {}).get("composite_score") or {}
    lines += [
        "",
        "## Result Evidence",
        f"- Composite score basis: {composite_evidence.get('why', 'not recorded')}",
        f"- Scored methods: {analysis.get('evidence_summary', {}).get('composite_score_evidence', {}).get('scored_method_count', 0)}",
        f"- Missing method evidence: {', '.join(analysis.get('evidence_summary', {}).get('missing_methods', [])) or 'none'}",
    ]
    lines += ["", "## Evidence", f"- Local documents: {len(evidence)}", f"- Public sources: {len(sources)}", ""]
    for item in evidence[:8]:
        lines.append(f"- {item['filename']}: {item.get('extraction_method')} ({item.get('sha256', '')[:12]})")
    lines += ["", "## Public Sources"]
    for source in sources:
        lines.append(f"- {source['title']}: {source['url']} ({source.get('source_quality_label', 'thin_signal')})")
    lines += ["", "## Research Gaps And Follow-Ups"]
    for item in research_gap_followups(analysis, sources):
        lines.append(f"- {item}")
    lines += ["", "## User Decision Boundary", "Use the scores, assumptions, and source refs to decide what to review next."]
    return "\n".join(lines) + "\n"


def build_research_coverage(research_ledgers: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    companies = []
    for company, ledger in sorted(research_ledgers.items()):
        stage_counts = {stage: len(sources) for stage, sources in ledger.items()}
        statuses = sorted({str(source.get("status") or "") for sources in ledger.values() for source in sources if source.get("status")})
        companies.append({
            "company_name": company,
            "company_slug": slugify(company),
            "stage_counts": stage_counts,
            "statuses": statuses,
        })
    return {"generated_at": utc_now_iso(), "companies": companies}


def build_method_coverage(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    companies = []
    for analysis in analyses:
        companies.append({
            "company_name": analysis["company_name"],
            "company_slug": analysis["company_slug"],
            "method_statuses": {method_id: method["status"] for method_id, method in analysis["methods"].items()},
            "missing_methods": analysis["evidence_summary"]["missing_methods"],
        })
    return {"generated_at": utc_now_iso(), "method_ids": METHOD_IDS, "companies": companies}


def build_actor_review_context(
    *,
    analyses: list[dict[str, Any]],
    company_work_queue: list[dict[str, Any]],
    research_coverage: dict[str, Any],
    method_coverage: dict[str, Any],
    processed_company_names: list[str],
    skipped_company_names: list[str],
    output_files: list[dict[str, Any]],
    active_knowledge: dict[str, Any] | None = None,
    knowledge_rag: dict[str, Any] | None = None,
    actor_rag_context: dict[str, Any] | None = None,
    max_context_chars: int = 12000,
) -> dict[str, Any]:
    company_summaries = []
    for analysis in analyses:
        company_summaries.append({
            "company_name": analysis["company_name"],
            "company_slug": analysis["company_slug"],
            "processing_status": analysis.get("processing_status"),
            "composite_score": analysis.get("composite_score"),
            "method_statuses": {method_id: method.get("status") for method_id, method in analysis.get("methods", {}).items()},
            "method_scores": {method_id: method.get("score") for method_id, method in analysis.get("methods", {}).items()},
            "method_evidence": {
                method_id: {
                    "memory_hook": method.get("memory_hook"),
                    "status_reason": (method.get("evidence_summary") or {}).get("status_reason"),
                    "evidence_ref_count": len(method.get("evidence_refs") or []),
                    "missing_evidence": method.get("missing_evidence") or [],
                    "assumptions": method.get("assumptions") or [],
                    "warnings": method.get("warnings") or [],
                }
                for method_id, method in analysis.get("methods", {}).items()
            },
            "missing_methods": (analysis.get("evidence_summary") or {}).get("missing_methods", []),
            "audit_warning_count": len((analysis.get("audit") or {}).get("warnings") or []),
            "research_reconciliation": {
                "confirmation_count": len((analysis.get("research_reconciliation") or {}).get("confirmations") or []),
                "contradiction_count": len((analysis.get("research_reconciliation") or {}).get("contradictions") or []),
                "missing_public_evidence_count": len((analysis.get("research_reconciliation") or {}).get("missing_public_evidence") or []),
            },
            "adaptive_research_plan": {
                "lane_ids": [lane.get("lane_id") for lane in (analysis.get("research_plan") or {}).get("lanes", [])],
                "github_url_count": len((analysis.get("research_plan") or {}).get("github_urls") or []),
                "known_public_url_count": len((analysis.get("research_plan") or {}).get("known_public_urls") or []),
                "signal_keys": sorted(
                    key
                    for key, value in ((analysis.get("research_plan") or {}).get("signals") or {}).items()
                    if value
                ),
            },
        })
    context = {
        "blueprint_id": BLUEPRINT_ID,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "active_knowledge": active_knowledge or {},
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "rag_context": actor_rag_context or {},
        "judge_rubric": list((active_knowledge or {}).get("judge_rubric") or JUDGE_RUBRIC),
        "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
        "company_count": len(analyses),
        "processed_company_names": processed_company_names,
        "skipped_company_names": skipped_company_names,
        "company_work_queue": [
            {
                "company_name": item.get("company_name"),
                "company_slug": item.get("company_slug"),
                "status": item.get("status"),
                "document_count": item.get("document_count"),
            }
            for item in company_work_queue
        ],
        "company_summaries": company_summaries,
        "research_coverage": research_coverage,
        "method_coverage": method_coverage,
        "output_files": [
            {"kind": item.get("kind"), "path": item.get("path"), "company_slug": item.get("company_slug")}
            for item in output_files[:50]
        ],
        "privacy_controls": {
            "public_research_queries": "company names, domains, categories, and non-confidential public claims only",
            "local_document_text": "not included in actor-review context",
        },
        "actor_review_focus": [
            "judge whether adaptive research lanes matched company-specific evidence",
            "flag missing GitHub, docs, profile, pricing, traction, or market follow-ups when signals were present",
            "verify source quality labels separate confirmation, conflict, blocked, thin, technical, and market-context signals",
        ],
    }
    if len(json.dumps(context, default=str)) <= max_context_chars:
        context["context_json_chars"] = len(json.dumps(context, default=str))
        return context
    compact_company_summaries = []
    for item in company_summaries:
        compact_company_summaries.append({
            "company_name": item.get("company_name"),
            "company_slug": item.get("company_slug"),
            "processing_status": item.get("processing_status"),
            "composite_score": item.get("composite_score"),
            "method_statuses": item.get("method_statuses"),
            "method_scores": item.get("method_scores"),
            "missing_methods": item.get("missing_methods"),
            "audit_warning_count": item.get("audit_warning_count"),
            "research_reconciliation": item.get("research_reconciliation"),
            "adaptive_research_plan": item.get("adaptive_research_plan"),
        })
    rag_citations = (actor_rag_context or {}).get("citations") if isinstance(actor_rag_context, dict) else []
    compact_context = {
        "blueprint_id": BLUEPRINT_ID,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "active_knowledge": active_knowledge_reference(active_knowledge or {}) if (active_knowledge or {}).get("content") else (active_knowledge or {}),
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "rag_context": {
            "enabled": (actor_rag_context or {}).get("enabled") if isinstance(actor_rag_context, dict) else False,
            "status": (actor_rag_context or {}).get("status") if isinstance(actor_rag_context, dict) else "",
            "citation_count": len(rag_citations or []),
            "citations": rag_citations[:5] if isinstance(rag_citations, list) else [],
        },
        "judge_rubric": list((active_knowledge or {}).get("judge_rubric") or JUDGE_RUBRIC),
        "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
        "company_count": len(analyses),
        "processed_company_names": processed_company_names,
        "skipped_company_names": skipped_company_names,
        "company_work_queue": context["company_work_queue"],
        "company_summaries": compact_company_summaries,
        "research_coverage": {
            "companies": (research_coverage or {}).get("companies", []),
            "generated_at": (research_coverage or {}).get("generated_at"),
        },
        "method_coverage": method_coverage,
        "output_files": context["output_files"][:30],
        "privacy_controls": context["privacy_controls"],
        "actor_review_focus": context["actor_review_focus"],
        "truncated_for_actor_review": True,
    }
    encoded = json.dumps(compact_context, default=str)
    if len(encoded) > max_context_chars:
        compact_context["output_files"] = compact_context["output_files"][:10]
        compact_context["actor_review_focus"] = compact_context["actor_review_focus"][:1]
    compact_context["context_json_chars"] = len(json.dumps(compact_context, default=str))
    return compact_context


def actor_prompt_spec(actor_id: str) -> dict[str, Any]:
    if actor_id in REVIEW_AGENT_PROMPT_SPECS:
        return dict(REVIEW_AGENT_PROMPT_SPECS[actor_id])
    if actor_id in RESEARCH_AGENT_PROMPT_SPECS:
        return {
            "mission": f"Review whether {actor_id} followed its specialist research mission and produced grounded, public-safe evidence.",
            "focus": [actor_id, "tool trace", "evidence gaps", "RAG refs"],
        }
    return {
        "mission": f"Review the {actor_id} workflow step for role-specific quality, evidence grounding, and clear gaps.",
        "focus": [actor_id, "workflow quality", "evidence grounding"],
    }


def build_actor_review_prompt(
    *,
    actor_id: str,
    actor_spec: dict[str, Any],
    context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    prompt_spec = actor_prompt_spec(actor_id)
    available_rag_refs = (context.get("rag_context") or {}).get("citations") if isinstance(context.get("rag_context"), dict) else []
    system_prompt = (
        f"You are {actor_id}, a VC Assistant specialist reviewer. "
        f"Mission: {prompt_spec['mission']} Return strict JSON only. "
        "Use RAG citation refs when supplied. Do not issue pass/watch/reject/buy/sell/invest recommendations."
    )
    return system_prompt, {
        "task": prompt_spec["mission"],
        "actor_id": actor_id,
        "configured_role": actor_spec.get("role") or actor_id,
        "configured_responsibilities": actor_spec.get("responsibilities") or [],
        "focus": prompt_spec.get("focus") or [],
        "rag_refs_required": knowledge_rag_is_required(knowledge_rag),
        "available_rag_refs": available_rag_refs,
        "context": context,
        "required_schema": {
            "summary": "short role-specific review summary",
            "findings": [
                {
                    "severity": "info|warning|error",
                    "message": "specific finding",
                    "company": "optional",
                    "method_id": "optional",
                    "evidence_ref": "optional",
                    "rag_refs": ["citation ref numbers used"],
                }
            ],
            "risks": ["role-specific residual risks"],
            "evidence_gaps": ["missing evidence or missing outputs"],
            "rag_refs": ["top-level citation ref numbers used"],
            "recommended_next_step": "one bounded next workflow action, no investment recommendation",
        },
    }


def default_actor_rag_refs(context: dict[str, Any]) -> list[Any]:
    rag_context = context.get("rag_context") if isinstance(context.get("rag_context"), dict) else {}
    return citation_ref_values(rag_context)


def not_llm_reviewed_actor_finding(actor_id: str, actor_spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor_id": actor_id,
        "role": actor_spec.get("role") or actor_id,
        "responsibilities": actor_spec.get("responsibilities") or [],
        "summary": "Deterministic workflow artifact was preserved; this actor was not selected for live LLM review in the current throughput profile.",
        "findings": [],
        "risks": [],
        "evidence_gaps": [],
        "rag_refs": [],
        "recommended_next_step": "Review deterministic outputs and selected live actor reviews.",
        "provider": "not_llm_reviewed",
        "model": "not_llm_reviewed",
        "status": "not_llm_reviewed",
        "generated_at": utc_now_iso(),
    }


def run_vc_actor_reviews(
    *,
    config: dict[str, Any],
    llm: Any,
    actor_ids: list[str] | tuple[str, ...] | set[str],
    state: dict[str, Any],
    context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
    event_sink: Path | None = None,
) -> dict[str, Any]:
    actor_specs = resolve_actor_specs(config, actor_ids=list(actor_ids))
    findings = state.setdefault("actor_findings", {})
    review_config = actor_review_config(config)
    selected_actor_ids = {actor_id for actor_id in review_config["llm_actor_ids"] if actor_id in set(actor_ids)}
    for actor_id in actor_ids:
        actor_id = str(actor_id)
        actor_spec = dict(actor_specs.get(actor_id) or {})
        if actor_id not in selected_actor_ids:
            findings[actor_id] = not_llm_reviewed_actor_finding(actor_id, actor_spec)
            if event_sink is not None:
                append_event(event_sink, "actor_activity", {"agent_id": actor_id, "status": "not_llm_reviewed", "summary": findings[actor_id]["summary"]})
            continue
        system_prompt, prompt = build_actor_review_prompt(
            actor_id=actor_id,
            actor_spec=actor_spec,
            context=context,
            knowledge_rag=knowledge_rag,
        )
        fallback = {
            "actor_id": actor_id,
            "summary": "Actor review unavailable; deterministic VC report artifacts were preserved.",
            "findings": [],
            "risks": [],
            "evidence_gaps": [],
            "rag_refs": [],
            "recommended_next_step": "Review deterministic outputs manually.",
            "confidence": 0.35,
        }
        with observed_operation(
            event_sink,
            phase="actor_review",
            operation=actor_id,
            agent_id=actor_id,
            prompt_hash=stable_text_hash(json.dumps(prompt, default=str)),
            prompt_chars=len(json.dumps(prompt, default=str)),
        ) as op:
            finding = llm.generate_json(system_prompt=system_prompt, user_prompt=json.dumps(prompt, default=str), fallback=fallback)
            op.close("completed", provider=finding.get("provider") if isinstance(finding, dict) else "", response_chars=len(json.dumps(finding, default=str)) if isinstance(finding, dict) else len(str(finding)))
        if not isinstance(finding, dict):
            raise RuntimeError(f"Actor {actor_id} returned non-object JSON.")
        if knowledge_rag_is_required(knowledge_rag) and not rag_ref_values(finding):
            refs = default_actor_rag_refs(context)
            if refs:
                finding["rag_refs"] = refs
                finding.setdefault("evidence_gaps", [])
                if isinstance(finding["evidence_gaps"], list):
                    finding["evidence_gaps"].append("Actor review omitted explicit RAG refs; refs were attached from the shared review context.")
        validate_llm_rag_refs(finding, knowledge_rag=knowledge_rag, stage=actor_id)
        finding.setdefault("actor_id", actor_id)
        finding.setdefault("role", actor_spec.get("role") or actor_id)
        finding.setdefault("responsibilities", actor_spec.get("responsibilities") or [])
        finding.setdefault("generated_at", utc_now_iso())
        findings[actor_id] = finding
        if event_sink is not None:
            append_event(event_sink, "actor_activity", {"agent_id": actor_id, "status": "completed", "summary": finding.get("summary")})
    return findings


def render_run_summary(analyses: list[dict[str, Any]], queue: list[dict[str, Any]], research_coverage: dict[str, Any], method_coverage: dict[str, Any]) -> str:
    skipped_count = sum(1 for item in queue if item["status"] == "unchanged_skipped")
    processed_count = len(queue) - skipped_count
    lines = [
        "# VC Assistant Run Summary",
        "",
        "Report-only run. The user decides what to review next.",
        "",
        f"Companies in index: {len(analyses)}",
        f"Companies processed this cycle: {processed_count}",
        f"Unchanged companies skipped: {skipped_count}",
        "",
        "## Company Scores",
    ]
    for analysis in analyses:
        lines.append(f"- {analysis['company_name']}: composite score {analysis['composite_score']}")
    lines += ["", "## Research Coverage"]
    for item in research_coverage["companies"]:
        lines.append(f"- {item['company_name']}: {item['stage_counts']}")
    lines += ["", "## Method Coverage"]
    for item in method_coverage["companies"]:
        lines.append(f"- {item['company_name']}: {item['method_statuses']}")
    return "\n".join(lines) + "\n"


def write_company_outputs(
    output_folder: Path,
    analyses: list[dict[str, Any]],
    company_records: dict[str, list[dict[str, Any]]],
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
    queue: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output_files = []
    for analysis in analyses:
        slug = analysis["company_slug"]
        company_dir = output_folder / slug
        evidence = company_records[analysis["company_name"]]
        research_ledger = research_ledgers[analysis["company_name"]]
        sources = flattened_sources(research_ledger)
        warnings = warnings_for_company(analysis, sources)
        write_json(company_dir / "analysis.json", analysis)
        write_json(company_dir / "method_scores.json", analysis["methods"])
        write_json(company_dir / "research_plan.json", analysis.get("research_plan") or {})
        write_json(company_dir / "agent_tool_trace.json", analysis.get("agent_tool_trace") or [])
        write_json(company_dir / "research_sources.json", sources)
        write_json(company_dir / "sources.json", sources)
        write_json(company_dir / "evidence.json", evidence)
        write_json(company_dir / "warnings.json", warnings)
        markdown = render_markdown(analysis, sources, evidence)
        (company_dir / "analysis.md").write_text(markdown, encoding="utf-8")
        for name in ("analysis.json", "analysis.md", "method_scores.json", "research_plan.json", "agent_tool_trace.json", "research_sources.json", "sources.json", "evidence.json", "warnings.json"):
            output_files.append({"kind": name.rsplit(".", 1)[0], "path": str(company_dir / name), "company": analysis["company_name"]})
        write_json(output_folder / "company_fact_tables" / f"{slug}.json", analysis["fact_table"])
        write_json(output_folder / "research_ledgers" / f"{slug}.json", research_ledger)
        write_json(output_folder / "method_scores" / f"{slug}.json", analysis["methods"])
        write_json(output_folder / "audit_findings" / f"{slug}.json", analysis["audit"])
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
    research_coverage = build_research_coverage(research_ledgers)
    method_coverage = build_method_coverage(analyses)
    write_json(output_folder / "company_index.json", index)
    write_json(output_folder / "company_work_queue.json", queue)
    write_json(output_folder / "research_coverage.json", research_coverage)
    write_json(output_folder / "method_coverage.json", method_coverage)
    index_lines = ["# VC Heuristic Company Index", "", "Report-only score summaries. The user decides what to do next.", ""]
    for item in index["companies"]:
        index_lines.append(f"- {item['company_name']}: composite score {item['composite_score']}")
    (output_folder / "company_index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    (output_folder / "run_summary.md").write_text(render_run_summary(analyses, queue, research_coverage, method_coverage), encoding="utf-8")
    output_files.extend([
        {"kind": "company_index_json", "path": str(output_folder / "company_index.json")},
        {"kind": "company_index_markdown", "path": str(output_folder / "company_index.md")},
        {"kind": "company_work_queue", "path": str(output_folder / "company_work_queue.json")},
        {"kind": "research_coverage", "path": str(output_folder / "research_coverage.json")},
        {"kind": "method_coverage", "path": str(output_folder / "method_coverage.json")},
        {"kind": "run_summary_markdown", "path": str(output_folder / "run_summary.md")},
    ])
    return output_files


def scoring_worker_count(config: dict[str, Any]) -> int:
    scoring = config.get("scoring") if isinstance(config.get("scoring"), dict) else {}
    return bounded_int(scoring.get("max_workers"), default=7, maximum=len(METHOD_IDS))


def company_worker_count(config: dict[str, Any], company_count: int) -> int:
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    return bounded_int(execution.get("max_company_workers"), default=min(4, max(1, company_count)), maximum=max(1, company_count))


def process_company_packet(
    *,
    company: str,
    records: list[dict[str, Any]],
    queue_item: dict[str, Any],
    output_folder: Path,
    resolved_config: dict[str, Any],
    run_dir: Path,
    action_budget: ActionBudget | None = None,
    llm: Any | None = None,
    knowledge_rag: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if queue_item["status"] == "unchanged_skipped":
        cached_analysis = load_cached_company_analysis(output_folder, company)
        cached_ledger = load_cached_research_ledger(output_folder, company)
        if cached_analysis and cached_ledger is not None:
            reconciliation = cached_analysis.get("research_reconciliation") or reconcile_research(records, cached_ledger)
            cached_analysis["processing_status"] = "unchanged_skipped"
            cached_analysis["cached_from_previous_run"] = True
            cached_analysis["research_reconciliation"] = reconciliation
            if "research_plan" not in cached_analysis:
                internet = resolved_config.get("internet_research") if isinstance(resolved_config.get("internet_research"), dict) else {}
                cached_analysis["research_plan"] = build_adaptive_research_plan(company, records, internet)
            cached_analysis.setdefault("agent_tool_trace", [])
            cached_analysis.setdefault("research_plan", {}).setdefault("knowledge_rag", public_knowledge_rag_state(knowledge_rag))
            return {
                "company_name": company,
                "analysis": cached_analysis,
                "research_ledger": cached_ledger,
                "reconciliation": reconciliation,
                "processed": False,
                "skipped": True,
            }
        queue_item["status"] = "new_or_changed"
        queue_item["cache_status"] = "missing_cached_report_reprocessed"

    internet = resolved_config.get("internet_research") if isinstance(resolved_config.get("internet_research"), dict) else {}
    research_plan = build_adaptive_research_plan(company, records, internet)
    agent_tool_trace: list[dict[str, Any]] = []
    research_ledger = call_with_supported_kwargs(
        research_company_by_stage,
        company=company,
        config=resolved_config,
        run_dir=run_dir,
        action_budget=action_budget,
        records=records,
        llm=llm,
        agent_tool_trace=agent_tool_trace,
        knowledge_rag=knowledge_rag,
    )
    append_financial_tool_research(company, records, research_ledger, action_budget=action_budget)
    reconciliation = reconcile_research(records, research_ledger)
    analysis = build_company_analysis(company, records, research_ledger, scoring_workers=scoring_worker_count(resolved_config))
    analysis["processing_status"] = "new_or_changed"
    analysis["cached_from_previous_run"] = False
    analysis["research_reconciliation"] = reconciliation
    analysis["research_plan"] = research_plan
    analysis["agent_tool_trace"] = agent_tool_trace
    analysis["research_plan"]["knowledge_rag"] = {
        **public_knowledge_rag_state(knowledge_rag),
        "agent_knowledge_refs": {
            item.get("agent_id"): item.get("knowledge_refs") or []
            for item in agent_tool_trace
            if item.get("knowledge_refs")
        },
    }
    analysis["research_plan"]["agentic_research"] = {
        "enabled": bool(agentic_research_config(resolved_config).get("enabled")),
        "agent_ids": agentic_research_config(resolved_config).get("agent_ids"),
        "allowed_tools": agentic_research_config(resolved_config).get("allowed_tools"),
        "max_iterations_per_agent": agentic_research_config(resolved_config).get("max_iterations_per_agent"),
        "max_tool_calls_per_agent": agentic_research_config(resolved_config).get("max_tool_calls_per_agent"),
        "stop_reasons": {item.get("agent_id"): item.get("stop_reason") for item in agent_tool_trace},
    }
    return {
        "company_name": company,
        "analysis": analysis,
        "research_ledger": research_ledger,
        "reconciliation": reconciliation,
        "processed": True,
        "skipped": False,
    }


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    blueprint_dir = Path(__file__).resolve().parents[3]
    resolved_config = load_resolved_config(blueprint_dir / "config" / "default.json", config)
    active_knowledge = load_vc_knowledge(blueprint_dir)
    active_knowledge_ref = active_knowledge_reference(active_knowledge)
    action_budget = build_action_budget(resolved_config)
    llm_limiter = build_llm_call_limiter(resolved_config)
    require_live_llm = llm_requires_live(resolved_config)
    payload = dict((resolved_config.get("inputs") or {}).get("payload") or {})
    if inputs:
        payload.update(inputs)
    run_id = run_id or payload.get("run_id") or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    output_folder = expand_runtime_path(payload.get("output_folder") or (resolved_config.get("outputs") or {}).get("folder_path") or f"outputs/{BLUEPRINT_ID}")
    run_dir = resolve_run_dir(output_folder, run_id, runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    document_folder = (
        resolve_existing_path(payload["document_folder"], [blueprint_dir, blueprint_dir.parent])
        if payload.get("document_folder")
        else blueprint_dir / "examples" / "sample_inputs"
    )
    monitoring = dict(payload.get("monitoring") or {})
    max_cycles = int(monitoring.get("max_cycles") or 1)

    write_json(run_dir / "config.json", resolved_config)
    write_json(run_dir / "inputs.json", {"payload": payload, "document_folder": str(document_folder)})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()})
    try:
        with observed_operation(run_dir, phase="llm_init", operation="actor_llm.init"):
            llm = BudgetedLLM(
                _get_configured_actor_llm(resolved_config, llm_client),
                action_budget,
                require_live=require_live_llm,
                limiter=llm_limiter,
                run_dir=run_dir,
            )
    except Exception as exc:
        append_event(run_dir, "tool_call_failed", {"tool": "actor_llm.init", "status": "required_actor_llm_init_failed", "error": str(exc)})
        write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "failed", "error": str(exc), "finished_at": utc_now_iso()})
        raise
    with observed_operation(
        run_dir,
        phase="knowledge_rag",
        operation="prepare",
        embedding_provider=((resolved_config.get("knowledge_rag") or {}).get("embedding_provider") if isinstance(resolved_config.get("knowledge_rag"), dict) else ""),
        embedding_model=((resolved_config.get("knowledge_rag") or {}).get("embedding_model") if isinstance(resolved_config.get("knowledge_rag"), dict) else ""),
    ) as op:
        knowledge_rag = prepare_knowledge_rag(
            blueprint_dir=blueprint_dir,
            resolved_config=resolved_config,
            active_knowledge=active_knowledge,
            run_dir=run_dir,
        )
        op.close(
            "completed",
            rag_status=knowledge_rag.get("status"),
            indexed_count=(knowledge_rag.get("index_summary") or {}).get("indexed_count") if isinstance(knowledge_rag.get("index_summary"), dict) else None,
        )
    try:
        require_ready_rag(knowledge_rag, stage="batch_indexing", run_dir=run_dir)
    except Exception as exc:
        append_event(run_dir, "tool_call_failed", {"tool": "knowledge_rag.index", "status": "required_rag_failed", "error": str(exc)})
        write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "failed", "error": str(exc), "finished_at": utc_now_iso()})
        raise
    append_event(run_dir, "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "watch_cycle_started", {"cycle": 1, "max_cycles": max_cycles})
    append_event(run_dir, "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})

    try:
        with observed_operation(run_dir, phase="document_intake", operation="scan_documents", path_hash=stable_text_hash(document_folder), supported_suffixes=sorted(SUPPORTED_SUFFIXES)) as op:
            company_records = scan_documents(document_folder, resolved_config)
            op.close("completed", company_count=len(company_records), document_count=sum(len(records) for records in company_records.values()))
    except OcrRequiredError as exc:
        append_event(run_dir, "tool_call_failed", {"tool": "llm_ocr.extract_document_folder", "status": "required_ocr_failed", "error": str(exc)})
        write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "failed", "error": str(exc), "finished_at": utc_now_iso()})
        raise
    if not company_records:
        company_records = {"Sample Startup": []}
    previous_state = load_watch_state(output_folder)
    company_work_queue = build_company_work_queue(company_records, previous_state)
    write_json(output_folder / "company_work_queue.json", company_work_queue)
    write_json(run_dir / "company_work_queue.json", company_work_queue)
    queue_by_company = {item["company_name"]: item for item in company_work_queue}
    sorted_company_items = sorted(company_records.items(), key=lambda item: slugify(item[0]))
    max_company_workers = company_worker_count(resolved_config, len(sorted_company_items))
    if max_company_workers <= 1 or len(sorted_company_items) <= 1:
        company_results = []
        for company, records in sorted_company_items:
            with observed_operation(run_dir, phase="company_processing", operation="process_company_packet", company=company, document_count=len(records)) as op:
                result = process_company_packet(
                    company=company,
                    records=records,
                    queue_item=queue_by_company[company],
                    output_folder=output_folder,
                    resolved_config=resolved_config,
                    run_dir=run_dir,
                    action_budget=action_budget,
                    llm=llm,
                    knowledge_rag=knowledge_rag,
                )
                op.close("completed", processed=result.get("processed"), skipped=result.get("skipped"))
                company_results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=max_company_workers, thread_name_prefix="vc-company") as executor:
            futures = {
                executor.submit(
                    process_company_packet,
                    company=company,
                    records=records,
                    queue_item=queue_by_company[company],
                    output_folder=output_folder,
                    resolved_config=resolved_config,
                    run_dir=run_dir,
                    action_budget=action_budget,
                    llm=llm,
                    knowledge_rag=knowledge_rag,
                ): company
                for company, records in sorted_company_items
            }
            company_results = [future.result() for future in as_completed(futures)]
    company_results = sorted(company_results, key=lambda item: item["analysis"]["company_slug"])
    analyses = [item["analysis"] for item in company_results]
    research_ledgers = {item["company_name"]: item["research_ledger"] for item in company_results}
    reconciliations = {item["company_name"]: item["reconciliation"] for item in company_results}
    processed_company_names = [item["company_name"] for item in company_results if item["processed"]]
    skipped_company_names = [item["company_name"] for item in company_results if item["skipped"]]
    output_files = write_company_outputs(output_folder, analyses, company_records, research_ledgers, company_work_queue)
    watch_state = update_watch_state(output_folder, run_dir, company_work_queue)
    append_event(run_dir, "startup_folder_watcher_completed", {"company_count": len(company_records)})
    append_event(run_dir, "company_packet_grouper_completed", {"company_count": len(company_work_queue)})
    append_event(
        run_dir,
        "document_evidence_extractor_completed",
        {
            "document_count": sum(len(company_records[company]) for company in processed_company_names),
            "skipped_company_count": len(skipped_company_names),
        },
    )
    append_event(run_dir, "claim_normalizer_completed", {"company_count": len(processed_company_names), "skipped_company_count": len(skipped_company_names)})
    append_event(run_dir, "research_planner_completed", {"company_count": len(processed_company_names), "skipped_company_count": len(skipped_company_names)})
    for stage in RESEARCH_STAGE_IDS:
        append_event(run_dir, f"{stage}_completed", {"company_count": len(processed_company_names), "skipped_company_count": len(skipped_company_names)})
    append_event(run_dir, "research_reconciler_completed", {"company_count": len(processed_company_names), "skipped_company_count": len(skipped_company_names)})
    for scorer_id in SCORER_STAGE_BY_METHOD.values():
        append_event(run_dir, f"{scorer_id}_completed", {"company_count": len(processed_company_names), "skipped_company_count": len(skipped_company_names)})
    append_event(run_dir, "score_consistency_auditor_completed", {"company_count": len(processed_company_names), "skipped_company_count": len(skipped_company_names)})
    append_event(run_dir, "company_report_writer_completed", {"output_folder": str(output_folder)})
    append_event(run_dir, "batch_index_writer_completed", {"output_folder": str(output_folder)})
    append_event(run_dir, "watch_cycle_completed", {"cycle": 1, "companies": len(company_records)})
    research_coverage = build_research_coverage(research_ledgers)
    method_coverage = build_method_coverage(analyses)
    actor_rag_context = retrieve_knowledge_rag_context(
        knowledge_rag=knowledge_rag,
        query=(
            "VC method correctness evidence grounding assumption clarity missing evidence honesty "
            "financial reasoning quality adaptive research plan quality source quality labels"
        ),
        stage="actor_review",
        run_dir=run_dir,
    )
    require_ready_rag(knowledge_rag, stage="actor_review", context=actor_rag_context, min_citations=1, run_dir=run_dir)
    actor_review_settings = actor_review_config(resolved_config)
    actor_context = build_actor_review_context(
        analyses=analyses,
        company_work_queue=company_work_queue,
        research_coverage=research_coverage,
        method_coverage=method_coverage,
        processed_company_names=processed_company_names,
        skipped_company_names=skipped_company_names,
        output_files=output_files,
        active_knowledge=active_knowledge_for_prompt(active_knowledge, knowledge_rag),
        knowledge_rag=knowledge_rag,
        actor_rag_context=actor_rag_context,
        max_context_chars=actor_review_settings["max_context_chars"],
    )
    actor_specs = resolve_actor_specs(resolved_config)
    actor_ids = [actor_id for actor_id in WORKFLOW_STEP_IDS if actor_id in actor_specs]
    actor_state: dict[str, Any] = {}
    actor_review_warnings = []
    try:
        actor_findings = run_vc_actor_reviews(
            config=resolved_config,
            llm=llm,
            actor_ids=actor_ids,
            state=actor_state,
            context=actor_context,
            knowledge_rag=knowledge_rag,
            event_sink=run_dir,
        )
    except Exception as exc:
        if require_live_llm or knowledge_rag_is_required(knowledge_rag):
            append_event(run_dir, "tool_call_failed", {"tool": "actor_llm", "status": "required_actor_review_failed", "error": str(exc)})
            write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "failed", "error": str(exc), "finished_at": utc_now_iso()})
            raise
        actor_findings = actor_review_unavailable_findings(actor_ids, exc)
        actor_review_warnings.append(
            {
                "kind": "actor_review",
                "status": "actor_review_unavailable",
                "message": "LLM actor review failed after deterministic reports were generated; report artifacts were preserved.",
                "error": str(exc),
            }
        )
        append_event(run_dir, "tool_call_failed", {"tool": "actor_llm", "status": "actor_review_unavailable", "error": str(exc)})
    unavailable_actor_errors = [
        str(finding.get("error") or "")
        for finding in actor_findings.values()
        if isinstance(finding, dict) and finding.get("provider") == "actor_review_unavailable"
    ]
    if unavailable_actor_errors and not actor_review_warnings:
        actor_review_warnings.append(
            {
                "kind": "actor_review",
                "status": "actor_review_unavailable",
                "message": "One or more LLM actor reviews failed after deterministic reports were generated; report artifacts were preserved.",
                "error": unavailable_actor_errors[0],
                "affected_actor_count": len(unavailable_actor_errors),
            }
        )
    action_ledger = action_budget.summary(include_actions=True)
    budget_warnings = []
    if action_ledger["exhausted"]:
        budget_warnings.append(
            {
                "kind": "budget",
                "status": "budget_exhausted",
                "message": "The VC Assistant action budget was exhausted; later research, financial-tool, or actor-review calls may be partial.",
            }
        )
    knowledge_rag_warnings = list(knowledge_rag.get("warnings") or [])

    final_artifact = {
        "type": OUTPUT_TYPE,
        "executive_summary": f"{BLUEPRINT_NAME} prepared score-only VC heuristic reports for {len(analyses)} startup companies; {len(skipped_company_names)} unchanged companies used cached reports.",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": 0.74 if any(item["composite_score"] is not None for item in analyses) else 0.35,
        "evidence": [record for records in company_records.values() for record in records[:5]],
        "next_steps": [
            "Review each company subfolder before deciding what to diligence next.",
            "Check insufficient_evidence method sections and add source documents where needed.",
            "Use public source refs only as context; verify material claims independently.",
        ],
        "source_refs": ["inputs.json", "events.jsonl", "llm_rag_trace.jsonl", "result.json", "final_artifact.json", "action_ledger.json", "company_index.json", KNOWLEDGE_PLAYBOOK_RELATIVE_PATH],
        "active_knowledge": active_knowledge_ref,
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "research_summary": {
            "company_count": len(research_ledgers),
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "privacy_policy": "no confidential excerpts in public research queries",
            "stage_ids": RESEARCH_STAGE_IDS,
            "coverage": research_coverage,
            "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        },
        "research_sources": [source for ledger in research_ledgers.values() for source in flattened_sources(ledger)],
        "research_warnings": [*budget_warnings, *knowledge_rag_warnings],
        "actor_review_warnings": actor_review_warnings,
        "report_only": True,
        "company_reports": analyses,
        "method_ids": METHOD_IDS,
        "workflow_step_ids": WORKFLOW_STEP_IDS,
        "company_work_queue": company_work_queue,
        "method_coverage": method_coverage,
        "parallel_execution": {
            "max_company_workers": max_company_workers,
            "max_stage_workers": bounded_int((resolved_config.get("internet_research") or {}).get("max_stage_workers"), default=len(RESEARCH_STAGE_IDS), maximum=len(RESEARCH_STAGE_IDS)),
            "max_scoring_workers": scoring_worker_count(resolved_config),
            "llm_backpressure": llm_limiter.config_summary(),
            "company_processing_order": [analysis["company_slug"] for analysis in analyses],
        },
        "actor_review": {
            "llm_actor_ids": actor_review_settings["llm_actor_ids"],
            "max_context_chars": actor_review_settings["max_context_chars"],
            "context_json_chars": actor_context.get("context_json_chars"),
        },
        "monitor_state": {
            "mode": "folder_monitoring",
            "cycles_completed": 1,
            "max_cycles": max_cycles,
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "watch_state": watch_state,
        },
        "output_files": output_files,
        "actor_findings": actor_findings,
        "llm_usage": llm_usage(llm),
        "action_ledger": action_ledger,
    }
    root_output_files = [
        {"kind": "final_artifact_json", "path": str(output_folder / "final_artifact.json")},
        {"kind": "action_ledger_json", "path": str(output_folder / "action_ledger.json")},
    ]
    final_artifact["output_files"] = [*output_files, *root_output_files]
    result = {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "final_artifact": final_artifact}

    append_event(run_dir, "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(run_dir, "human_input_requested", {"mode": "approval_required", "reason": "Reports contain heuristic investment-analysis scores for human review only."})
    append_event(run_dir, "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    with observed_operation(run_dir, phase="writing_artifacts", operation="write_final_outputs", output_file_count=len(final_artifact["output_files"])):
        write_json(output_folder / "final_artifact.json", final_artifact)
        write_json(output_folder / "action_ledger.json", action_ledger)
        write_json(run_dir / "result.json", result)
        write_json(run_dir / "final_artifact.json", final_artifact)
        write_json(run_dir / "action_ledger.json", action_ledger)
    append_event(run_dir, "artifact_written", {"path": str(output_folder / "final_artifact.json")})
    append_event(run_dir, "artifact_written", {"path": str(output_folder / "action_ledger.json")})
    append_event(run_dir, "artifact_written", {"path": "result.json"})
    append_event(run_dir, "artifact_written", {"path": "final_artifact.json"})
    append_event(run_dir, "artifact_written", {"path": "action_ledger.json"})
    if (run_dir / "llm_rag_trace.jsonl").exists():
        append_event(run_dir, "artifact_written", {"path": "llm_rag_trace.jsonl"})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()})
    return result


def run_runtime_step(
    step_id: str,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    if step_id == "startup_folder_watcher":
        result = run_blueprint(inputs=inputs, config=config, runs_root=runs_root, run_id=run_id, llm_client=llm_client)
        result["workflow_step_id"] = step_id
        result["runtime_step_mode"] = "report_factory_entrypoint"
        return result

    runtime_run_id = run_id or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    run_dir = resolve_run_dir(Path("/tmp") / runtime_run_id, runtime_run_id, runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    append_event(
        run_dir,
        f"{step_id}_completed",
        {
            "step_id": step_id,
            "runtime_step_mode": "acknowledged_after_report_factory_entrypoint",
            "note": "The startup_folder_watcher service step runs the complete VC report factory once; this DAG node is represented for workflow observability.",
        },
    )
    result = {
        "run_id": runtime_run_id,
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "workflow_step_id": step_id,
        "runtime_step_mode": "acknowledged_after_report_factory_entrypoint",
    }
    write_json(run_dir / f"{step_id}_result.json", result)
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
    step_id = os.environ.get("MN_WORKFLOW_STEP_ID", "").strip()
    if step_id:
        result = run_runtime_step(step_id, inputs=inputs, runs_root=args.runs_root or None, run_id=args.run_id or None)
    else:
        result = run_blueprint(inputs=inputs, runs_root=args.runs_root or None, run_id=args.run_id or None)
    printable = {"run_id": result["run_id"], "status": result["status"]}
    if "workflow_step_id" in result:
        printable["workflow_step_id"] = result["workflow_step_id"]
    if "runtime_step_mode" in result:
        printable["runtime_step_mode"] = result["runtime_step_mode"]
    if "final_artifact" in result:
        printable["final_artifact"] = result["final_artifact"]
    print(json.dumps(printable, indent=2))


if __name__ == "__main__":
    main()
