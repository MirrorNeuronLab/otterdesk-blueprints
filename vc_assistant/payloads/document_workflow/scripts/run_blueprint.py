#!/usr/bin/env python3.11

import argparse
from dataclasses import asdict, dataclass
import html as html_lib
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse


RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-llm-ocr-skill",
    "mirrorneuron-rag-skill",
    "mirrorneuron-w3m-browser-skill",
    "mirrorneuron-web-browser-skill",
    "mirrorneuron-evidence-engine-skill",
    "mirrorneuron-actor-review-skill",
    "mirrorneuron-client-report-skill",
    "mirrorneuron-document-reading-skill",
    "mirrorneuron-public-research-orchestrator-skill",
    "mirrorneuron-scoring-framework-skill",
)


def _bootstrap_runtime() -> None:
    for parent in Path(__file__).resolve().parents:
        helper = parent / "otterdesk_blueprint_env.py"
        if helper.exists():
            spec = importlib.util.spec_from_file_location("otterdesk_blueprint_env", helper)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.bootstrap_blueprint_runtime(__file__, packages=RUNTIME_SKILL_PACKAGES)
            return


_bootstrap_runtime()

from mn_blueprint_support import (
    PromptLibrary,
    append_event_jsonl,
    get_actor_llm_client,
    llm_usage,
    load_resolved_config as load_shared_resolved_config,
    resolve_actor_specs,
    run_actor_reviews,
    start_agent_beacon_thread,
)

try:
    from mn_context_engine_sdk import MemoryItem, WorkingMemory
except Exception:  # pragma: no cover - optional runtime support
    MemoryItem = None
    WorkingMemory = None

from mn_evidence_engine_skill import (
    ClaimRecord,
    EvidenceItem,
    SourceRecord,
    aggregate_claim_records,
    apply_evidence_score_caps,
    build_bayesian_claim_explanations,
    build_evidence_graph,
    build_evidence_items_from_texts,
    build_source_reliability_records,
    claim_type_prior,
    clamp_score,
    combine_claim_truth_probability,
    confidence_band,
    crowdkit_true_probability,
    dimension_score_from_claims,
    run_dawid_skene_truth_discovery,
    score_evidence_quality,
    stable_short_id,
    to_dict,
)
from mn_actor_review_skill import (
    actor_review_unavailable_findings,
    default_actor_rag_refs as shared_default_actor_rag_refs,
    normalize_actor_review_warnings as shared_normalize_actor_review_warnings,
    truncate_for_prompt as _truncate_for_prompt,
)
from mn_client_report_skill import (
    build_research_coverage as shared_build_research_coverage,
    markdown_cell,
    quality_check as shared_quality_check,
)
from mn_document_reading_skill import (
    document_paths as shared_document_paths,
    records_fingerprint,
    safe_read_text,
)
from mn_public_research_orchestrator_skill import (
    annotate_agent_sources as shared_annotate_agent_sources,
    budget_exhausted_source as shared_budget_exhausted_source,
    compact_company_report_for_transport as shared_compact_company_report_for_transport,
    compact_local_evidence_for_transport as shared_compact_local_evidence_for_transport,
    compact_research_sources_for_transport as shared_compact_research_sources_for_transport,
    compact_text as shared_compact_text,
    dedupe_list,
    extract_domains,
    host_from_url,
    lane as shared_lane,
    observation_from_sources as shared_observation_from_sources,
    source_record as shared_source_record,
    validate_agent_tool_call as shared_validate_agent_tool_call,
)
from mn_scoring_framework_skill import (
    evidence_status,
    keyword_score,
    money_values,
    run_scorers,
    source_refs_from_records,
    source_refs_from_sources,
)


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
DEFAULT_ACTION_BUDGET = 80
DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS = 10.0
DEFAULT_ACTOR_REVIEW_LLM_ACTOR_IDS = [
    "research_reconciler",
    "score_consistency_auditor",
    "company_report_writer",
    "batch_index_writer",
]
DEFAULT_ACTOR_REVIEW_CONTEXT_TARGET_TOKENS = 1200
DEFAULT_ACTOR_REVIEW_CONTEXT_TOKEN_BUDGET = 3000
MAX_TRANSPORT_EVIDENCE_PER_COMPANY = 20
MAX_TRANSPORT_SOURCES_PER_COMPANY = 80
MAX_TRANSPORT_SNIPPET_CHARS = 1200
MAX_TRANSPORT_TEXT_PREVIEW_CHARS = 600
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
CLAIM_TYPES = [
    "team.founder_background",
    "team.domain_expertise",
    "product.prototype",
    "product.technical_depth",
    "market.buyer_segment",
    "market.size",
    "traction.pilots",
    "traction.paid_customers",
    "traction.revenue.arr",
    "traction.retention",
    "traction.pipeline",
    "moat.ip",
    "moat.data",
    "moat.distribution",
    "finance.round_terms",
    "finance.burn",
    "finance.runway",
    "risk.competition",
    "risk.sales_cycle",
    "risk.manufacturing",
    "risk.regulatory",
]
FUND_PROFILE_WEIGHTS = {
    "seed_saas": {
        "team": 0.20,
        "market": 0.15,
        "product": 0.15,
        "traction": 0.25,
        "moat": 0.10,
        "financial": 0.05,
        "risk": 0.10,
    },
    "deeptech": {
        "team": 0.20,
        "market": 0.15,
        "product": 0.20,
        "traction": 0.15,
        "moat": 0.15,
        "financial": 0.05,
        "risk": 0.10,
    },
    "generalist": {
        "team": 0.20,
        "market": 0.15,
        "product": 0.15,
        "traction": 0.25,
        "moat": 0.10,
        "financial": 0.05,
        "risk": 0.10,
    },
}
VC_SOURCE_TYPE_BETA_PRIORS = {
    "data_room_document": {"alpha": 16, "beta": 3},
    "founder_document": {"alpha": 7, "beta": 6},
    "founder_provided_document": {"alpha": 7, "beta": 6},
    "deterministic_financial_tool": {"alpha": 7, "beta": 8},
    "government_registry": {"alpha": 18, "beta": 3},
    "public_article": {"alpha": 7, "beta": 5},
    "public_profile": {"alpha": 6, "beta": 6},
    "public_web_page": {"alpha": 6, "beta": 6},
}
VC_CLAIM_TYPE_PRIORS = {
    "product.prototype": 0.65,
    "product.demo_available": 0.60,
    "traction.pilots": 0.45,
    "traction.paid_customers": 0.35,
    "traction.revenue.arr": 0.30,
    "traction.enterprise_contracts": 0.25,
    "traction.retention": 0.25,
    "traction.pipeline": 0.35,
    "moat.patent_filing": 0.45,
    "moat.granted_patent": 0.35,
    "moat.proprietary_dataset": 0.40,
    "team.founder_background": 0.50,
    "team.domain_expertise": 0.45,
    "finance.round_terms": 0.35,
    "finance.burn": 0.40,
    "finance.runway": 0.40,
}
VC_BAYESIAN_CRITICAL_CLAIM_TYPES = {
    "traction.revenue.arr",
    "traction.paid_customers",
    "traction.enterprise_contracts",
    "traction.retention",
    "traction.pilots",
    "product.prototype",
    "product.demo_available",
    "moat.proprietary_dataset",
    "finance.round_terms",
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

PROMPTS = PromptLibrary.from_script(__file__, parents_up=2)
RESEARCH_AGENT_PROMPT_FILES = {
    "research_planner": "research-planner.md",
    "company_identity_researcher": "company-identity-researcher.md",
    "funding_researcher": "funding-researcher.md",
    "market_comp_researcher": "market-comp-researcher.md",
    "traction_verifier": "traction-verifier.md",
    "rendered_page_researcher": "rendered-page-researcher.md",
}
REVIEW_AGENT_PROMPT_FILES = {
    "research_reconciler": "research-reconciler.md",
    "score_consistency_auditor": "score-consistency-auditor.md",
    "company_report_writer": "company-report-writer.md",
    "batch_index_writer": "batch-index-writer.md",
}


def load_prompt(name: str, **values: Any) -> str:
    return PROMPTS.load(name, **values)


def prompt_spec_from_markdown(name: str, **values: Any) -> dict[str, Any]:
    return PROMPTS.spec_from_markdown(name, **values)


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


def read_json_value(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


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


def resolve_output_folder(payload: dict[str, Any], resolved_config: dict[str, Any], inputs: dict[str, Any] | None = None) -> Path:
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output_folder:
        return expand_runtime_path(runtime_output_folder)
    explicit_output_folder = (inputs or {}).get("output_folder")
    if explicit_output_folder:
        return expand_runtime_path(explicit_output_folder)
    outputs_config = resolved_config.get("outputs") if isinstance(resolved_config.get("outputs"), dict) else {}
    configured_output_folder = outputs_config.get("output_folder") or outputs_config.get("folder_path")
    configured_target = payload.get("output_folder") or configured_output_folder
    if configured_target:
        return expand_runtime_path(configured_target)
    return expand_runtime_path(f"outputs/{BLUEPRINT_ID}")


def vc_knowledge_search_roots(blueprint_dir: Path) -> list[Path]:
    roots = [blueprint_dir, blueprint_dir / "payloads"]
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
    config = with_runtime_knowledge_rag_defaults(config)
    if fake_skills_mode_enabled(config):
        raw = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
        return {
            "enabled": True,
            "status": "mock_ready",
            "required": False,
            "mocked": True,
            "config": {
                "namespace": raw.get("namespace", "vc_assistant_context"),
                "top_k": raw.get("top_k", 3),
                "max_context_chars": raw.get("max_context_chars", 3000),
                "required": False,
            },
        }
    _load_rag_skill()
    return skill_knowledge_rag_config(config)


def with_runtime_knowledge_rag_defaults(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        return config

    raw = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
    updates: dict[str, Any] = {}
    if raw.get("enabled", True) and not str(raw.get("backend") or "").strip():
        updates["backend"] = "milvus_lite"

    runtime_db_root = (os.environ.get("MN_RAG_DB_ROOT") or "").strip()
    if runtime_db_root and not str(raw.get("db_root") or "").strip():
        updates["db_root"] = runtime_db_root

    if not updates:
        return config

    patched = dict(config)
    patched["knowledge_rag"] = {**raw, **updates}
    return patched


def resolve_knowledge_dir(blueprint_dir: Path, active_knowledge: dict[str, Any]) -> Path:
    if fake_skills_mode_enabled():
        return blueprint_dir / "knowledge"
    _load_rag_skill()
    return skill_resolve_blueprint_knowledge_dir(blueprint_dir, active_knowledge=active_knowledge)


def prepare_knowledge_rag(
    *,
    blueprint_dir: Path,
    resolved_config: dict[str, Any],
    active_knowledge: dict[str, Any],
    run_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_config = with_runtime_knowledge_rag_defaults(resolved_config)
    raw = resolved_config.get("knowledge_rag") if isinstance(resolved_config.get("knowledge_rag"), dict) else {}
    if fake_skills_mode_enabled(resolved_config):
        state = {
            "enabled": True,
            "status": "mock_ready",
            "required": False,
            "mocked": True,
            "warnings": [],
            "config": {
                "namespace": raw.get("namespace", "vc_assistant_context"),
                "embedding_provider": "mock",
                "embedding_model": "mock-deterministic-rag",
                "top_k": raw.get("top_k", 3),
                "max_context_chars": raw.get("max_context_chars", 3000),
                "index_on_startup": False,
                "required": False,
            },
        }
        append_observation_record(
            run_dir,
            "skill_mock_used",
            {
                "phase": "knowledge_rag",
                "operation": "prepare",
                "tool": "rag_skill",
                "status": "mocked",
                "mocked": True,
            },
        )
        return state
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
    if quick_test_mode_enabled(resolved_config):
        return {
            "enabled": False,
            "status": "disabled",
            "required": False,
            "warnings": [
                {
                    "kind": "knowledge_rag",
                    "status": "disabled_for_quick_test",
                    "message": "Knowledge RAG embedding calls are disabled during quick-test runs; bundled static VC knowledge was used instead.",
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
            "message": "Knowledge RAG was enabled but Milvus Lite indexing could not complete; no static playbook fallback was injected.",
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
    if isinstance(state, dict) and state.get("mocked"):
        return {key: value for key, value in state.items() if not key.startswith("_")}
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
    if isinstance(knowledge_rag, dict) and knowledge_rag.get("mocked"):
        return context if context is not None else knowledge_rag
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
    if fake_skills_mode_enabled() or (isinstance(knowledge_rag, dict) and knowledge_rag.get("mocked")):
        with observed_operation(run_dir, phase="knowledge_rag", operation="retrieve", mocked=True, **metadata) as op:
            ref = f"mock-rag:{slugify(stage or 'stage')}:{stable_text_hash(company or query)[:8]}"
            context = {
                "enabled": True,
                "status": "mock_ready",
                "mocked": True,
                "query": query,
                "context": f"Mock VC knowledge context for {company or stage}: use evidence-backed scoring, note assumptions, and keep recommendations review-only.",
                "citations": [
                    {
                        "ref": ref,
                        "title": "Mock VC assistant knowledge",
                        "source": "fake_skills",
                        "score": 1.0,
                    }
                ],
            }
            op.close("completed", mocked=True, rag_status=context["status"], citation_count=1, context_chars=len(context["context"]))
            return context
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
    append_event_jsonl(run_dir, event_type, payload, lock=EVENT_LOCK)


def append_resource_record(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": observation_payload(**payload)}
    with TRACE_LOCK:
        with (run_dir / "resources.jsonl").open("a", encoding="utf-8") as handle:
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


def append_debug_record(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": observation_payload(**payload)}
    with TRACE_LOCK:
        with (run_dir / "debug_trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    append_event(run_dir, event_type, record["payload"])


def append_debug_record_if_enabled(ctx: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
    if debug_mode_enabled(ctx.get("config") if isinstance(ctx, dict) else None):
        append_debug_record(ctx.get("run_dir"), event_type, payload)


def observation_trace_summary(run_dir: Path | None, *, tail_limit: int = 20) -> dict[str, Any]:
    trace_path = run_dir / "llm_rag_trace.jsonl" if run_dir is not None else None
    if trace_path is None or not trace_path.exists():
        return {
            "trace_artifact": "llm_rag_trace.jsonl",
            "trace_available": False,
            "record_count": 0,
            "event_type_counts": {},
            "status_counts": {},
            "operation_counts": {},
            "llm_call_count": 0,
            "rag_operation_count": 0,
            "tool_operation_count": 0,
            "failed_operation_count": 0,
            "tail": [],
        }
    event_type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    operation_counts: dict[str, int] = {}
    tail: list[dict[str, Any]] = []
    record_count = 0
    llm_call_count = 0
    rag_operation_count = 0
    tool_operation_count = 0
    failed_operation_count = 0
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_count += 1
        event_type = str(record.get("type") or "unknown")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        status = str(payload.get("status") or "")
        operation = str(payload.get("operation") or "")
        phase = str(payload.get("phase") or "")
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
        if operation:
            operation_counts[operation] = operation_counts.get(operation, 0) + 1
        if "llm" in event_type or "llm" in operation or payload.get("agent_id"):
            llm_call_count += 1
        if "rag" in phase or "rag" in operation or payload.get("citation_count") is not None:
            rag_operation_count += 1
        if payload.get("tool") or "tool" in event_type or "browser" in operation:
            tool_operation_count += 1
        if event_type.endswith("_failed") or status in {"failed", "error"}:
            failed_operation_count += 1
        tail_record = {
            "type": event_type,
            "timestamp": record.get("timestamp"),
            "phase": phase,
            "operation": operation,
            "status": status,
            "agent_id": payload.get("agent_id"),
            "company": payload.get("company"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "prompt_chars": payload.get("prompt_chars") or payload.get("user_prompt_chars"),
            "response_chars": payload.get("response_chars"),
            "prompt_hash": payload.get("prompt_hash"),
            "query_hash": payload.get("query_hash"),
            "query_length": payload.get("query_length"),
            "citation_count": payload.get("citation_count"),
            "tool": payload.get("tool"),
            "http_status": payload.get("http_status"),
            "error_type": payload.get("error_type"),
            "elapsed_ms": payload.get("elapsed_ms"),
        }
        tail.append(observation_payload(**tail_record))
        if len(tail) > tail_limit:
            tail = tail[-tail_limit:]
    return {
        "trace_artifact": "llm_rag_trace.jsonl",
        "trace_available": True,
        "record_count": record_count,
        "event_type_counts": event_type_counts,
        "status_counts": status_counts,
        "operation_counts": operation_counts,
        "llm_call_count": llm_call_count,
        "rag_operation_count": rag_operation_count,
        "tool_operation_count": tool_operation_count,
        "failed_operation_count": failed_operation_count,
        "tail": tail,
        "privacy": "metadata_only_no_prompts_no_raw_rag_context_no_document_text",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _iso_to_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_ms(started_at: Any, ended_at: Any) -> float | None:
    start = _iso_to_datetime(started_at)
    end = _iso_to_datetime(ended_at)
    if start is None or end is None:
        return None
    return round(max((end - start).total_seconds(), 0.0) * 1000, 2)


def _benchmark_step_records(run_dir: Path) -> list[dict[str, Any]]:
    starts: dict[str, dict[str, Any]] = {}
    completed: list[dict[str, Any]] = []
    for record in _read_jsonl(run_dir / "events.jsonl"):
        event_type = str(record.get("type") or "")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        step_id = str(payload.get("step_id") or "")
        if not step_id:
            continue
        if event_type == "benchmark_step_started":
            starts[step_id] = record
        elif event_type in {"benchmark_step_completed", "benchmark_step_failed"}:
            started = starts.get(step_id, {})
            started_at = started.get("timestamp") or payload.get("started_at")
            ended_at = record.get("timestamp") or payload.get("ended_at")
            completed.append(
                {
                    "step_id": step_id,
                    "status": "failed" if event_type.endswith("_failed") else str(payload.get("status") or "completed"),
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "elapsed_ms": payload.get("elapsed_ms") or _elapsed_ms(started_at, ended_at),
                }
            )
    return completed


def _benchmark_skill_records(run_dir: Path) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for record in _read_jsonl(run_dir / "llm_rag_trace.jsonl"):
        event_type = str(record.get("type") or "")
        if event_type not in {"observability_operation_completed", "observability_operation_failed"}:
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        phase = str(payload.get("phase") or "")
        operation = str(payload.get("operation") or "")
        if not phase and not operation:
            continue
        skills.append(
            {
                "phase": phase,
                "operation": operation,
                "tool": payload.get("tool"),
                "agent_id": payload.get("agent_id"),
                "company": payload.get("company"),
                "status": "failed" if event_type.endswith("_failed") else str(payload.get("status") or "completed"),
                "elapsed_ms": payload.get("elapsed_ms"),
                "mocked": bool(payload.get("mocked")),
            }
        )
    return skills


def write_benchmark_artifacts(run_dir: Path, *, run_id: str, status: str = "running") -> dict[str, Any]:
    steps = _benchmark_step_records(run_dir)
    skills = _benchmark_skill_records(run_dir)
    slowest_steps = sorted(steps, key=lambda item: float(item.get("elapsed_ms") or 0), reverse=True)[:5]
    slowest_skills = sorted(skills, key=lambda item: float(item.get("elapsed_ms") or 0), reverse=True)[:10]
    benchmark = {
        "schema": "mn.blueprint.benchmark.v1",
        "run_id": run_id,
        "blueprint_id": BLUEPRINT_ID,
        "started_at": steps[0].get("started_at") if steps else "",
        "generated_at": utc_now_iso(),
        "status": status,
        "steps": steps,
        "skills": skills,
        "totals": {
            "step_count": len(steps),
            "skill_call_count": len(skills),
            "total_step_elapsed_ms": round(sum(float(item.get("elapsed_ms") or 0) for item in steps), 2),
            "mocked_skill_call_count": sum(1 for item in skills if item.get("mocked")),
            "slowest_step": slowest_steps[0] if slowest_steps else None,
            "slowest_skill_operations": slowest_skills,
        },
    }
    write_json(run_dir / "benchmark.json", benchmark)
    write_benchmark_markdown(run_dir / "benchmark.md", benchmark)
    return benchmark


def write_benchmark_markdown(path: Path, benchmark: dict[str, Any]) -> None:
    lines = [
        f"# VC Assistant Benchmark",
        "",
        f"- Run ID: `{benchmark.get('run_id')}`",
        f"- Status: `{benchmark.get('status')}`",
        f"- Generated: `{benchmark.get('generated_at')}`",
        "",
        "## Steps",
        "",
        "| Step | Status | Elapsed ms |",
        "| --- | --- | ---: |",
    ]
    for step in benchmark.get("steps") or []:
        lines.append(f"| {step.get('step_id', '')} | {step.get('status', '')} | {step.get('elapsed_ms', '')} |")
    lines.extend(["", "## Skills", "", "| Phase | Operation | Status | Mocked | Elapsed ms |", "| --- | --- | --- | --- | ---: |"])
    for skill in benchmark.get("skills") or []:
        lines.append(
            f"| {skill.get('phase', '')} | {skill.get('operation', '')} | {skill.get('status', '')} | {str(bool(skill.get('mocked'))).lower()} | {skill.get('elapsed_ms', '')} |"
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def final_artifact_for_transport(final_artifact: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded artifact shape printed to the runtime workflow chain."""
    compact = dict(final_artifact)
    compact.pop("research_sources", None)
    compact.pop("evidence", None)
    reports = compact.get("company_reports")
    if isinstance(reports, list):
        compact["company_reports"] = [
            compact_company_report_for_transport(report) if isinstance(report, dict) else report
            for report in reports
        ]
    ledger = compact.get("action_ledger")
    if isinstance(ledger, dict):
        compact["action_ledger"] = {key: value for key, value in ledger.items() if key != "actions"}
    compact["transport"] = {
        "compacted": True,
        "omitted_fields": ["top_level.research_sources", "top_level.evidence", "action_ledger.actions"],
        "reason": "Prevent repeated workflow handoff payloads from growing Redis job state; detailed per-company artifacts remain in output files.",
    }
    return compact


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


def _api_base_kind(api_base: Any) -> str:
    value = str(api_base or "").strip()
    if not value:
        return "unknown"
    parsed = urlparse(value)
    host = parsed.hostname or value
    if "12434" in value or "/engines/" in value:
        return "docker_model_runner"
    if "11434" in value:
        return "ollama"
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "local_openai_compatible"
    return "remote_openai_compatible"


def _llm_usage_event_fields(llm: Any) -> dict[str, Any]:
    usage = getattr(llm, "last_usage", {}) or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "usage_estimated": bool(usage.get("estimated")),
        "usage_source": str(usage.get("source") or "unknown"),
        "usage_provider": str(usage.get("provider") or getattr(llm, "provider", "unknown")),
        "usage_model": str(usage.get("model") or getattr(llm, "model", "unknown")),
    }


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
        if self._require_live and hasattr(self._llm, "strict"):
            setattr(self._llm, "strict", True)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        actor_id = str(fallback.get("actor_id") or system_prompt or "actor_review")
        provider_name = getattr(self._llm, "provider", "unknown")
        model_name = getattr(self._llm, "model", "unknown")
        api_base = getattr(self._llm, "api_base", "")
        prompt_metadata = {
            "agent_id": actor_id,
            "provider": provider_name,
            "model": model_name,
            "api_base_kind": _api_base_kind(api_base),
            "request_status": "scheduled",
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
            usage_fields = _llm_usage_event_fields(self._llm)
            completion_metadata = {
                "provider": provider,
                "model": model_name,
                "api_base_kind": _api_base_kind(api_base),
                "request_status": "completed",
                "response_chars": response_chars,
                "limiter_wait_seconds": round(limiter_wait_seconds, 3),
                **usage_fields,
            }
            if self._require_live and (not provider_is_live(provider) or budget_status in {"budget_exhausted", "llm_call_failed"}):
                self._action_budget.complete(action, "failed", {**completion_metadata, "budget_status": budget_status})
                op.close(
                    "failed",
                    **completion_metadata,
                    budget_status=budget_status or "non_live_provider",
                    budget_after=self._action_budget.summary(include_actions=False),
                )
                raise RuntimeError(f"Required live LLM call for {actor_id} returned non-live provider '{provider or 'unknown'}'.")
            self._action_budget.complete(action, "completed", completion_metadata)
            append_resource_record(
                self._run_dir,
                "llm_usage",
                {"agent_id": actor_id, "operation": "actor_llm.generate_json", **completion_metadata},
            )
            op.close(
                "completed",
                **completion_metadata,
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
    if any(env_flag_enabled(name) for name in ("MN_BLUEPRINT_FAKE_LLM", "OTTERDESK_FAKE_LLM", "MN_USE_FAKE_LLM")):
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


def fake_skills_mode_enabled(config: dict[str, Any] | None = None) -> bool:
    if any(env_flag_enabled(name) for name in ("MN_BLUEPRINT_FAKE_SKILLS", "OTTERDESK_FAKE_SKILLS")):
        return True
    execution = (config or {}).get("execution") if isinstance((config or {}).get("execution"), dict) else {}
    testing = (config or {}).get("testing") if isinstance((config or {}).get("testing"), dict) else {}
    return any(
        str(value or "").strip().lower() in {"1", "true", "yes", "on", "fake", "mock", "stub"}
        for value in (execution.get("fake_skills"), testing.get("fake_skills"))
    )


def benchmark_mode_enabled(config: dict[str, Any] | None = None) -> bool:
    if env_flag_enabled("MN_BLUEPRINT_BENCHMARK"):
        return True
    execution = (config or {}).get("execution") if isinstance((config or {}).get("execution"), dict) else {}
    testing = (config or {}).get("testing") if isinstance((config or {}).get("testing"), dict) else {}
    return any(
        str(value or "").strip().lower() in {"1", "true", "yes", "on"}
        for value in (execution.get("benchmark"), testing.get("benchmark"))
    )


def debug_mode_enabled(config: dict[str, Any] | None = None) -> bool:
    if any(env_flag_enabled(name) for name in ("MN_BLUEPRINT_DEBUG", "MN_DEBUG", "OTTERDESK_DEBUG")):
        return True
    execution = (config or {}).get("execution") if isinstance((config or {}).get("execution"), dict) else {}
    testing = (config or {}).get("testing") if isinstance((config or {}).get("testing"), dict) else {}
    return any(
        str(value or "").strip().lower() in {"1", "true", "yes", "on", "debug", "verbose"}
        for value in (execution.get("debug"), testing.get("debug"))
    )


def call_with_supported_kwargs(func: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return func(**kwargs)
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return func(**supported)


def _script_blueprint_root() -> Path:
    script_path = Path(__file__).resolve()
    if len(script_path.parents) > 3 and script_path.parents[2].name == "payloads":
        return script_path.parents[3]
    if len(script_path.parents) > 2:
        return script_path.parents[2]
    return script_path.parent


def default_config_path() -> Path:
    configured_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if configured_path:
        candidate = expand_runtime_path(configured_path)
        if candidate.exists():
            return candidate

    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        candidate = expand_runtime_path(bundle_dir) / "config" / "default.json"
        if candidate.exists():
            return candidate

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "config" / "default.json"
        if candidate.exists():
            return candidate
    return _script_blueprint_root() / "config" / "default.json"


def resolve_blueprint_dir() -> Path:
    return default_config_path().parents[1]


def _merge_config(base: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    if not overlay:
        return base
    merged = json.loads(json.dumps(base))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_resolved_config(default_path: Path | None = None, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_default_path = default_path or default_config_path()
    if resolved_default_path.exists():
        return load_shared_resolved_config(resolved_default_path, overlay=overlay)

    embedded_config = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if embedded_config:
        decoded = json.loads(embedded_config)
        if isinstance(decoded, dict):
            return _merge_config(decoded, overlay)
    return load_shared_resolved_config(resolved_default_path, overlay=overlay)


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
        "MN_LLM_RUNTIME_MODEL": llm_config.get("runtime_model") or primary.get("runtime_model"),
        "MN_LLM_API_BASE": llm_config.get("api_base") or primary.get("api_base"),
        "MN_LLM_BACKEND": llm_config.get("backend") or primary.get("backend"),
        "MN_LLM_CONTEXT_SIZE": llm_config.get("context_size") or primary.get("context_size"),
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


def redactor(text: str) -> str:
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", text or "")
    value = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", value)
    value = re.sub(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED-PHONE]", value)
    return value


class OcrRequiredError(RuntimeError):
    pass


def startup_packet_classifier(text: str, filename: str) -> str:
    del text, filename
    return "startup_packet"


def _document_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return shared_document_paths(folder, supported_suffixes=SUPPORTED_SUFFIXES)


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve())


def _llm_ocr_records_for_pdfs(folder: Path, pdf_paths: list[Path], config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not pdf_paths:
        return {}
    if fake_skills_mode_enabled(config):
        records_by_path: dict[str, dict[str, Any]] = {}
        for path in pdf_paths:
            company = infer_company_name(path, path.stem, folder)
            records_by_path[_path_key(path)] = {
                "path": str(path),
                "text": (
                    f"Company: {company}\n"
                    "Mock OCR text generated by --fake-skills for blueprint logic testing.\n"
                    "Product: AI workflow automation platform.\n"
                    "Market: enterprise productivity and startup operations.\n"
                    "Traction: pilot customers, early revenue signals, and active founder-led sales.\n"
                    "Risks: mock source data must be replaced with real document extraction before investment decisions.\n"
                ),
                "warnings": ["fake_skills mock OCR record"],
                "extraction_method": "fake_llm_ocr_skill",
                "ocr_required": False,
                "mocked": True,
            }
        return records_by_path
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
    return records_fingerprint(records)


def load_watch_state(output_folder: Path) -> dict[str, Any]:
    state = read_json(output_folder / "watch_state.json")
    companies = state.get("companies")
    if not isinstance(companies, dict):
        state["companies"] = {}
    return state


def force_reprocess_enabled(payload: dict[str, Any], config: dict[str, Any]) -> bool:
    cache_config = config.get("cache_policy") if isinstance(config.get("cache_policy"), dict) else {}
    payload_policy = payload.get("cache_policy") if isinstance(payload.get("cache_policy"), dict) else {}
    candidates = [
        payload.get("force_reprocess"),
        payload.get("force_refresh"),
        payload_policy.get("force_reprocess"),
        cache_config.get("force_reprocess"),
    ]
    if any(str(value).strip().lower() in {"1", "true", "yes", "on"} for value in candidates if value is not None):
        return True
    return any(env_flag_enabled(name) for name in ("VC_ASSISTANT_FORCE_REPROCESS", "MN_BLUEPRINT_FORCE_REPROCESS", "MN_FORCE_REPROCESS"))


def build_company_work_queue(company_records: dict[str, list[dict[str, Any]]], previous_state: dict[str, Any], *, force_reprocess: bool = False) -> list[dict[str, Any]]:
    previous_companies = previous_state.get("companies") if isinstance(previous_state.get("companies"), dict) else {}
    queue = []
    for company, records in sorted(company_records.items(), key=lambda item: slugify(item[0])):
        slug = slugify(company)
        fingerprint = company_fingerprint(records)
        previous = previous_companies.get(slug) if isinstance(previous_companies.get(slug), dict) else {}
        unchanged = previous.get("fingerprint") == fingerprint
        use_cached = unchanged and not force_reprocess
        previous_run_id = previous.get("last_run_id") or previous_state.get("run_id")
        cache_policy = {
            "company_slug": slug,
            "fingerprint": fingerprint,
            "previous_fingerprint": previous.get("fingerprint"),
            "previous_run_id": previous_run_id,
            "cache_source": "watch_state_and_company_artifacts" if use_cached else "",
            "freshness": "unchanged_cached" if use_cached else ("forced_reprocess" if force_reprocess and unchanged else "fresh_or_changed"),
            "force_reprocess": bool(force_reprocess),
            "decision": "reuse_cached_outputs" if use_cached else "process_company_packet",
        }
        queue.append(
            {
                "company_id": slug,
                "company_name": company,
                "company_slug": slug,
                "fingerprint": fingerprint,
                "document_count": len(records),
                "status": "unchanged_skipped" if use_cached else "new_or_changed",
                "previous_fingerprint": previous.get("fingerprint"),
                "previous_run_id": previous_run_id,
                "cache_policy": cache_policy,
                "source_refs": [record.get("path") for record in records],
            }
        )
    return queue


def update_watch_state(output_folder: Path, run_dir: Path, queue: list[dict[str, Any]], *, run_id: str) -> dict[str, Any]:
    state = {
        "run_id": run_id,
        "updated_at": utc_now_iso(),
        "companies": {
            item["company_slug"]: {
                "company_name": item["company_name"],
                "fingerprint": item["fingerprint"],
                "status": item["status"],
                "document_count": item["document_count"],
                "last_run_id": run_id,
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


def build_cache_policy_summary(queue: list[dict[str, Any]], *, processed_company_names: list[str], skipped_company_names: list[str]) -> dict[str, Any]:
    force_reprocess = any(bool((item.get("cache_policy") or {}).get("force_reprocess")) for item in queue)
    return {
        "enabled": True,
        "force_reprocess": force_reprocess,
        "processed_company_count": len(processed_company_names),
        "skipped_company_count": len(skipped_company_names),
        "fresh_run": len(skipped_company_names) == 0,
        "companies": [
            {
                "company_name": item.get("company_name"),
                "company_slug": item.get("company_slug"),
                "status": item.get("status"),
                "fingerprint": item.get("fingerprint"),
                "previous_fingerprint": item.get("previous_fingerprint"),
                "previous_run_id": item.get("previous_run_id"),
                "cache_source": (item.get("cache_policy") or {}).get("cache_source"),
                "freshness": (item.get("cache_policy") or {}).get("freshness"),
                "decision": (item.get("cache_policy") or {}).get("decision"),
            }
            for item in queue
        ],
    }


def is_substantive_public_source(source: dict[str, Any]) -> bool:
    status = str(source.get("status") or "").lower()
    url = str(source.get("url") or "")
    snippet = str(source.get("snippet") or "")
    if status in NON_SUBSTANTIVE_SOURCE_STATUSES:
        return False
    if not url.startswith(("http://", "https://")):
        return False
    return bool(snippet.strip())


@dataclass
class CompanyEvidenceSummary:
    company_slug: str
    investment_score: int | None
    evidence_quality_score: int
    confidence_band: str
    recommendation: str
    dimension_scores: dict[str, int]
    score_caps: list[dict[str, Any]]
    claim_count: int
    evidence_count: int


def source_record_type_from_local(record: dict[str, Any]) -> str:
    filename = str(record.get("filename") or "").lower()
    if any(term in filename for term in ("contract", "invoice", "bank", "customer")):
        return "data_room_document"
    return "founder_provided_document"


def public_source_type(source: dict[str, Any]) -> str:
    status = str(source.get("status") or "").lower()
    url = str(source.get("url") or "").lower()
    title = str(source.get("title") or "").lower()
    skill = str(source.get("skill") or "").lower()
    if status in {"blocked", "failed", "skill_unavailable", "budget_exhausted", "disabled", "error"}:
        return "blocked_page" if status == "blocked" else "failed_fetch"
    if url.startswith("financial_tool://"):
        return "deterministic_financial_tool"
    if "duckduckgo.com" in url or "google.com/search" in url or "bing.com/search" in url or "search results" in title:
        return "search_result_page"
    if any(domain in url for domain in ("sec.gov", "uspto.gov", "patents.google.com", "bls.gov", "sba.gov")):
        return "government_registry"
    if "crunchbase.com" in url or "linkedin.com" in url:
        return "public_profile"
    if "case stud" in title or "customer" in title:
        return "customer_case_study"
    if "browser_search" in skill and not url.startswith(("http://", "https://")):
        return "search_result_page"
    return "public_web_page"


def source_quality_score_for_type(source_type: str, source: dict[str, Any] | None = None) -> int:
    status = str((source or {}).get("status") or "").lower()
    if source_type in {"blocked_page", "failed_fetch"} or status in {"blocked", "failed", "skill_unavailable", "budget_exhausted", "disabled", "error"}:
        return 0
    if source_type == "data_room_document":
        return 95
    if source_type == "government_registry":
        return 90
    if source_type == "customer_case_study":
        return 85
    if source_type == "public_article":
        return 70
    if source_type == "company_website":
        return 60
    if source_type == "public_profile":
        return 55
    if source_type == "founder_provided_document":
        return 50
    if source_type == "search_result_page":
        return 5
    if source_type == "deterministic_financial_tool":
        return 45
    return 55


def extraction_quality_score_for_source(source_type: str, status: str, text: str, extraction_method: str = "") -> int:
    lowered_status = str(status or "").lower()
    if source_type in {"blocked_page", "failed_fetch"} or lowered_status in {"blocked", "failed", "skill_unavailable", "budget_exhausted", "disabled", "error"}:
        return 0
    if source_type == "search_result_page":
        return 10
    if not str(text or "").strip():
        return 0
    if "ocr" in str(extraction_method or "").lower():
        return 65
    if source_type == "founder_provided_document":
        return 95
    if len(str(text or "")) < 160:
        return 35
    return 75


def build_source_records(company: str, records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    company_slug = slugify(company)
    source_records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        source_type = source_record_type_from_local(record)
        source_id = stable_short_id("src", company_slug, record.get("path"), record.get("sha256"))
        item = SourceRecord(
            source_id=source_id,
            company_slug=company_slug,
            source_type=source_type,
            title=str(record.get("filename") or record.get("path") or "local document"),
            source_url=None,
            filename=str(record.get("filename") or ""),
            status="ok" if int(record.get("character_count") or 0) > 0 else "failed",
            source_quality_score=source_quality_score_for_type(source_type, record),
            extraction_quality_score=extraction_quality_score_for_source(
                source_type,
                "ok" if int(record.get("character_count") or 0) > 0 else "failed",
                str(record.get("text_preview") or ""),
                str(record.get("extraction_method") or ""),
            ),
            retrieved_at=utc_now_iso(),
            source_quality_label="local_claim",
        )
        value = to_dict(item)
        source_records.append(value)
        by_id[source_id] = value
    for source in sources:
        source_type = public_source_type(source)
        source_id = stable_short_id("src", company_slug, source.get("url"), source.get("title"), source.get("retrieved_at"))
        status = str(source.get("status") or "unknown")
        item = SourceRecord(
            source_id=source_id,
            company_slug=company_slug,
            source_type=source_type,
            title=str(source.get("title") or source.get("url") or "public source"),
            source_url=str(source.get("url") or "") or None,
            filename=None,
            status=status,
            source_quality_score=source_quality_score_for_type(source_type, source),
            extraction_quality_score=extraction_quality_score_for_source(source_type, status, str(source.get("snippet") or "")),
            retrieved_at=str(source.get("retrieved_at") or utc_now_iso()),
            source_quality_label=str(source.get("source_quality_label") or infer_source_quality_label(status, str(source.get("skill") or ""), str(source.get("verification_target") or ""), str(source.get("url") or ""), str(source.get("snippet") or ""))),
        )
        value = to_dict(item)
        source_records.append(value)
        by_id[source_id] = value
    return source_records, by_id


CLAIM_EXTRACTION_SPECS = [
    {
        "claim_type": "team.founder_background",
        "terms": ["founder", "cofounder", "team", "advisor", "operator"],
        "importance": 80,
        "motion": 0.55,
        "required": ["founder resume", "public founder profile", "reference call"],
    },
    {
        "claim_type": "team.domain_expertise",
        "terms": ["domain expert", "industry experience", "ex-", "operator", "engineer"],
        "importance": 75,
        "motion": 0.60,
        "required": ["public work history", "domain references", "prior outcomes"],
    },
    {
        "claim_type": "product.prototype",
        "terms": ["prototype", "mvp", "working", "demo", "launched", "product"],
        "importance": 85,
        "motion": 0.65,
        "required": ["demo", "usage logs", "technical review"],
    },
    {
        "claim_type": "product.technical_depth",
        "terms": ["api", "sdk", "model", "infrastructure", "hardware", "platform", "technology"],
        "importance": 70,
        "motion": 0.50,
        "required": ["architecture review", "repository or docs", "technical diligence"],
    },
    {
        "claim_type": "market.buyer_segment",
        "terms": ["buyer", "customer segment", "enterprise", "smb", "vertical", "market"],
        "importance": 70,
        "motion": 0.40,
        "required": ["ICP notes", "customer discovery calls", "pipeline segmentation"],
    },
    {
        "claim_type": "market.size",
        "terms": ["tam", "sam", "market size", "large market", "industry"],
        "importance": 70,
        "motion": 0.35,
        "required": ["market model", "credible industry source", "bottom-up TAM"],
    },
    {
        "claim_type": "traction.pilots",
        "terms": ["pilot", "pilots", "trial", "poc"],
        "importance": 85,
        "motion": 0.70,
        "required": ["pilot agreement", "active pilot status", "conversion plan"],
    },
    {
        "claim_type": "traction.paid_customers",
        "terms": ["paid customer", "paying customer", "customer", "contract"],
        "importance": 95,
        "motion": 0.80,
        "required": ["customer contract", "invoice", "customer reference"],
    },
    {
        "claim_type": "traction.revenue.arr",
        "terms": ["arr", "revenue", "mrr", "sales"],
        "importance": 95,
        "motion": 0.85,
        "required": ["customer contract", "invoice", "bank deposit", "ARR spreadsheet", "customer reference"],
    },
    {
        "claim_type": "traction.retention",
        "terms": ["retention", "renewal", "churn", "usage"],
        "importance": 85,
        "motion": 0.65,
        "required": ["cohort data", "renewal records", "usage export"],
    },
    {
        "claim_type": "traction.pipeline",
        "terms": ["pipeline", "qualified lead", "sales cycle", "opportunity"],
        "importance": 75,
        "motion": 0.45,
        "required": ["CRM export", "stage definitions", "conversion history"],
    },
    {
        "claim_type": "moat.ip",
        "terms": ["patent", "ip", "proprietary", "trade secret"],
        "importance": 70,
        "motion": 0.45,
        "required": ["patent filing", "IP assignment", "technical novelty review"],
    },
    {
        "claim_type": "moat.data",
        "terms": ["dataset", "data moat", "proprietary data", "exclusive data"],
        "importance": 65,
        "motion": 0.45,
        "required": ["data rights", "data provenance", "customer data permissions"],
    },
    {
        "claim_type": "moat.distribution",
        "terms": ["partner", "partnership", "distribution", "channel"],
        "importance": 75,
        "motion": 0.55,
        "required": ["partner agreement", "channel metrics", "co-sell evidence"],
    },
    {
        "claim_type": "finance.round_terms",
        "terms": ["round", "seed", "pre-seed", "valuation", "raise", "funding"],
        "importance": 65,
        "motion": 0.20,
        "required": ["term sheet", "cap table", "financing docs"],
    },
    {
        "claim_type": "finance.burn",
        "terms": ["burn", "monthly spend", "opex"],
        "importance": 70,
        "motion": -0.35,
        "required": ["bank statements", "budget", "payroll export"],
    },
    {
        "claim_type": "finance.runway",
        "terms": ["runway", "cash runway", "cash balance"],
        "importance": 70,
        "motion": 0.30,
        "required": ["cash balance", "forecast", "bank statements"],
    },
    {
        "claim_type": "risk.competition",
        "terms": ["competition", "competitor", "crowded", "incumbent"],
        "importance": 80,
        "motion": -0.50,
        "required": ["competitor map", "win/loss notes", "differentiation proof"],
    },
    {
        "claim_type": "risk.sales_cycle",
        "terms": ["sales cycle", "long sales", "procurement", "enterprise sales"],
        "importance": 75,
        "motion": -0.55,
        "required": ["sales cycle history", "pipeline aging", "procurement plan"],
    },
    {
        "claim_type": "risk.manufacturing",
        "terms": ["manufacturing", "supply chain", "hardware cost", "bom"],
        "importance": 75,
        "motion": -0.60,
        "required": ["BOM", "supplier quote", "manufacturing plan"],
    },
    {
        "claim_type": "risk.regulatory",
        "terms": ["regulatory", "compliance", "hipaa", "gdpr", "soc 2", "security"],
        "importance": 75,
        "motion": -0.50,
        "required": ["compliance scope", "attestation", "security review"],
    },
]


def negative_claim_polarity(sentence: str) -> bool:
    lowered = sentence.lower()
    return bool(re.search(r"\b(no|not|none|without|missing|lacks?|unverified|unconfirmed|failed|blocked)\b", lowered))


def extract_claim_value(sentence: str, claim_type: str) -> tuple[float | int | None, str | None]:
    if claim_type == "traction.revenue.arr":
        match = re.search(r"\$?\s?(\d+(?:\.\d+)?)\s?(k|m|thousand|million)?\s*(arr|mrr|revenue)?", sentence, flags=re.I)
        if match:
            value = float(match.group(1))
            suffix = (match.group(2) or "").lower()
            if suffix in {"m", "million"}:
                value *= 1_000_000
            elif suffix in {"k", "thousand"}:
                value *= 1_000
            unit = "USD_ARR" if "arr" in sentence.lower() else "USD_REVENUE"
            return int(value), unit
    if claim_type in {"traction.paid_customers", "traction.pilots"}:
        match = re.search(r"\b(\d+)\b", sentence)
        if match:
            return int(match.group(1)), "count"
    return None, None


def directness_for_claim(sentence: str, claim_type: str) -> int:
    lowered = sentence.lower()
    if claim_type == "traction.revenue.arr" and ("$" in sentence or "arr" in lowered):
        return 90
    if claim_type in {"traction.paid_customers", "traction.pilots"} and re.search(r"\b\d+\b", sentence):
        return 85
    if any(term in lowered for term in ("claims", "says", "reports", "plans", "targets")):
        return 70
    return 60


def specificity_for_claim(sentence: str, claim_type: str) -> int:
    if "$" in sentence or re.search(r"\b\d+\b", sentence):
        return 90
    if claim_type.startswith(("traction.", "finance.")):
        return 70
    if len(sentence.split()) >= 8:
        return 60
    return 45


def verification_status_for_evidence(source_type: str, claim_type: str, penalties: dict[str, int]) -> str:
    if source_type in {"blocked_page", "failed_fetch"}:
        return "insufficient_evidence"
    if "self_reported" in penalties and claim_type.startswith(("traction.", "finance.")):
        return "self_reported_unverified"
    if source_type in {"government_registry", "customer_case_study", "data_room_document"}:
        return "externally_supported"
    if source_type in {"public_profile", "public_web_page", "company_website"}:
        return "unverified"
    return "usable_but_unverified"


def evidence_penalties_for_claim(source_record: dict[str, Any], claim_type: str, _sentence: str) -> dict[str, int]:
    source_type = str(source_record.get("source_type") or "")
    penalties: dict[str, int] = {}
    if source_type == "founder_provided_document":
        penalties["self_reported"] = 10
    if claim_type in {"traction.revenue.arr", "finance.round_terms", "finance.burn", "finance.runway"} and source_type not in {"data_room_document", "government_registry"}:
        penalties["unverified_financial_claim"] = 15
    if source_type == "search_result_page":
        penalties["search_result_only"] = 20
    return penalties


def polarity_for_claim_sentence(sentence: str) -> str:
    return "contradicts" if negative_claim_polarity(sentence) else "supports"


def build_evidence_items(company: str, records: list[dict[str, Any]], sources: list[dict[str, Any]], source_records_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    company_slug = slugify(company)
    source_texts: list[dict[str, Any]] = []

    local_source_lookup = {
        stable_short_id("src", company_slug, record.get("path"), record.get("sha256")): record
        for record in records
    }
    for source_id, record in local_source_lookup.items():
        if source_id in source_records_by_id:
            source_texts.append({
                "source_id": source_id,
                "text": str(record.get("text_preview") or ""),
                "filename": str(record.get("filename") or ""),
                "source_url": None,
                "retrieved_at": utc_now_iso(),
                "recency_score": 50,
            })
    public_source_lookup = {
        stable_short_id("src", company_slug, source.get("url"), source.get("title"), source.get("retrieved_at")): source
        for source in sources
    }
    for source_id, source in public_source_lookup.items():
        if source_id in source_records_by_id:
            source_texts.append({
                "source_id": source_id,
                "text": str(source.get("snippet") or ""),
                "filename": None,
                "source_url": str(source.get("url") or "") or None,
                "retrieved_at": str(source.get("retrieved_at") or utc_now_iso()),
                "recency_score": 50,
            })

    return build_evidence_items_from_texts(
        company_slug=company_slug,
        source_texts=source_texts,
        source_records_by_id=source_records_by_id,
        claim_specs=CLAIM_EXTRACTION_SPECS,
        directness_resolver=directness_for_claim,
        specificity_resolver=specificity_for_claim,
        polarity_resolver=polarity_for_claim_sentence,
        penalties_resolver=evidence_penalties_for_claim,
        verification_status_resolver=verification_status_for_evidence,
    )


def required_next_evidence_for_claim(claim_type: str) -> list[str]:
    for spec in CLAIM_EXTRACTION_SPECS:
        if spec["claim_type"] == claim_type:
            return list(spec["required"])
    return ["independent supporting source", "primary document", "reference check"]


def motion_for_claim(claim_type: str, polarity: str) -> tuple[str, float]:
    strength = 0.0
    for spec in CLAIM_EXTRACTION_SPECS:
        if spec["claim_type"] == claim_type:
            strength = float(spec["motion"])
            break
    if polarity == "contradicts":
        strength = -strength
    if strength > 0.05:
        return "positive", round(strength, 2)
    if strength < -0.05:
        return "negative", round(strength, 2)
    return "neutral", 0.0


def canonical_claim_key(ev: dict[str, Any]) -> str:
    claim_type = str(ev.get("claim_type") or "")
    value, unit = extract_claim_value(str(ev.get("claim_text") or ""), claim_type)
    if value is not None:
        return f"{claim_type}:{unit}:{value}"
    text = re.sub(r"\W+", " ", str(ev.get("claim_text") or "").lower()).strip()
    return f"{claim_type}:{text[:80]}"


def claim_dimension(claim_type: str) -> str:
    root = str(claim_type or "").split(".", 1)[0]
    return "financial" if root == "finance" else root


def fund_profile_weights(fund_profile: str | None) -> dict[str, float]:
    key = str(fund_profile or "generalist").strip().lower().replace("-", "_")
    return FUND_PROFILE_WEIGHTS.get(key) or FUND_PROFILE_WEIGHTS["generalist"]


def apply_company_score_caps(raw_score: int | None, claims: list[dict[str, Any]], evidence_quality: int, fund_profile: str) -> tuple[int | None, list[dict[str, Any]]]:
    if raw_score is None:
        return None, []
    score, cap_codes = apply_evidence_score_caps(int(raw_score), claims, evidence_quality, fund_profile)
    cap_messages = {
        "no_founder_info_cap_65": (65, "No founder or team evidence was found."),
        "no_customer_or_traction_cap_55": (55, "No customer or traction evidence was found."),
        "no_product_or_prototype_cap_50": (50, "No product or prototype evidence was found."),
        "low_evidence_quality_cap_45": (45, "Evidence quality is below 30, so the score is not reliable."),
    }
    caps = [
        {"cap": cap_messages.get(code, (score, code))[0], "reason": cap_messages.get(code, (score, code))[1], "code": code}
        for code in cap_codes
    ]
    return score, caps


def source_prior_adjusted_claim_probability(
    claim: dict[str, Any],
    evidence_by_id: dict[str, EvidenceItem],
    source_reliability_by_id: dict[str, float],
) -> float:
    support = 0.0
    contradiction = 0.0
    for evidence_id in claim.get("evidence_ids") or []:
        evidence = evidence_by_id.get(str(evidence_id))
        if evidence is None:
            continue
        reliability = source_reliability_by_id.get(evidence.source_id, 0.5)
        weight = reliability * ((evidence.confidence_score or 0) / 100)
        polarity = str(getattr(evidence.polarity, "value", evidence.polarity) or "")
        if polarity == "supports":
            support += weight
        elif polarity == "contradicts":
            contradiction += weight
    total = support + contradiction
    if total > 0:
        return max(0.0, min(1.0, support / total))
    return max(0.0, min(1.0, int(claim.get("net_confidence") or 0) / 100))


def build_truth_discovery_layer(
    company_slug: str,
    evidence_items: list[dict[str, Any]],
    claim_records: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings: list[str] = []
    typed_evidence: list[EvidenceItem] = []
    for item in evidence_items:
        data = dict(item)
        data["claim_id"] = str(data.get("claim_id") or stable_short_id("claim", company_slug, canonical_claim_key(item)))
        try:
            typed_evidence.append(EvidenceItem(**data))
        except Exception as exc:
            warnings.append(f"could_not_parse_evidence:{data.get('evidence_id') or 'unknown'}:{type(exc).__name__}")
    try:
        truth_result = run_dawid_skene_truth_discovery(typed_evidence)
    except Exception as exc:
        return {
            "eligible_claim_ids": [],
            "predicted_labels": {},
            "claim_probabilities": {},
            "source_reliability": [],
            "claim_truth_scores": [],
            "warnings": warnings + [f"truth_discovery_failed:{type(exc).__name__}"],
            "notes": ["Truth discovery could not run; use phase-one evidence confidence only."],
        }

    typed_sources: list[SourceRecord] = []
    for source in source_records:
        try:
            typed_sources.append(SourceRecord(**dict(source)))
        except Exception as exc:
            warnings.append(f"could_not_parse_source:{source.get('source_id') or 'unknown'}:{type(exc).__name__}")
    reliability_records = build_source_reliability_records(
        typed_sources,
        truth_result.source_reliability_scores,
        source_type_beta_priors=VC_SOURCE_TYPE_BETA_PRIORS,
    )
    reliability_by_source = {
        record.source_id: float(record.combined_reliability if record.combined_reliability is not None else record.prior_reliability)
        for record in reliability_records
    }
    evidence_by_id = {evidence.evidence_id: evidence for evidence in typed_evidence}

    claim_truth_scores: list[dict[str, Any]] = []
    for claim in claim_records:
        claim_id = str(claim.get("claim_id") or "")
        posterior = int(claim.get("net_confidence") or 0) / 100
        source_prior_prob = source_prior_adjusted_claim_probability(claim, evidence_by_id, reliability_by_source)
        try:
            claim_model = ClaimRecord(
                **{
                    **dict(claim),
                    "prior_probability": claim_type_prior(
                        str(claim.get("claim_type") or ""),
                        claim_type_priors=VC_CLAIM_TYPE_PRIORS,
                    ),
                    "posterior_probability": posterior,
                }
            )
            final_probability = combine_claim_truth_probability(
                claim_model,
                source_prior_adjusted_prob=source_prior_prob,
                claim_probabilities=truth_result.claim_probabilities,
            )
        except Exception as exc:
            warnings.append(f"could_not_combine_claim_truth:{claim_id or 'unknown'}:{type(exc).__name__}")
            final_probability = posterior
        crowdkit_prob = crowdkit_true_probability(claim_id, truth_result.claim_probabilities)
        if claim_id in truth_result.eligible_claim_ids:
            note = "Crowd-Kit truth discovery used."
        else:
            note = "Skipped: not enough independent eligible sources."
        claim_truth_scores.append(
            {
                "claim_id": claim_id,
                "claim": claim.get("canonical_claim"),
                "log_odds_probability": round(posterior, 3),
                "crowdkit_probability": None if crowdkit_prob is None else round(crowdkit_prob, 3),
                "source_prior_adjusted_probability": round(source_prior_prob, 3),
                "final_truth_probability": round(final_probability, 3),
                "note": note,
            }
        )

    notes = []
    if truth_result.eligible_claim_ids:
        notes.append(f"Truth discovery used for {len(truth_result.eligible_claim_ids)} claim(s) with enough independent sources.")
    else:
        notes.append("Crowd-Kit was skipped because no claims had enough independent eligible sources.")
    if any("self_reported" in (item.get("penalties") or {}) for item in evidence_items):
        notes.append("Founder-provided claims remain self-reported until externally verified.")
    return {
        "eligible_claim_ids": truth_result.eligible_claim_ids,
        "predicted_labels": truth_result.predicted_labels,
        "claim_probabilities": truth_result.claim_probabilities,
        "source_reliability": [to_dict(record) for record in reliability_records],
        "claim_truth_scores": claim_truth_scores,
        "warnings": warnings + truth_result.warnings,
        "notes": notes,
    }


def build_bayesian_explainability_layer(
    company_name: str,
    evidence_items: list[dict[str, Any]],
    claim_records: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    truth_discovery: dict[str, Any],
) -> list[dict[str, Any]]:
    source_reliability_by_id = {
        str(record.get("source_id")): float(record.get("combined_reliability") or record.get("prior_reliability") or 0.50)
        for record in truth_discovery.get("source_reliability") or []
        if record.get("source_id")
    }
    try:
        return build_bayesian_claim_explanations(
            company_name=company_name,
            claims=claim_records,
            evidence_items=evidence_items,
            sources=source_records,
            source_reliability_by_id=source_reliability_by_id,
            claim_type_priors=VC_CLAIM_TYPE_PRIORS,
            critical_claim_types=VC_BAYESIAN_CRITICAL_CLAIM_TYPES,
            min_importance=80,
            max_claims=4,
        )
    except Exception as exc:
        return [
            {
                "status": "failed",
                "warning": f"bayesian_explainability_failed:{type(exc).__name__}",
                "message": "Bayesian claim explainability could not run; use the evidence table and truth-discovery section instead.",
            }
        ]


def recommendation_for_company(score: int | None, evidence_quality: int, caps: list[dict[str, Any]]) -> str:
    if score is None or evidence_quality < 20:
        return "too_early_to_score_confidently"
    if caps:
        return "diligence_first_verify_key_claims"
    if score >= 70 and evidence_quality >= 60:
        return "prioritize_for_diligence"
    if score >= 55:
        return "watchlist_with_targeted_diligence"
    return "needs_material_evidence_before_prioritizing"


def build_company_evidence_layer(
    company: str,
    records: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    fund_profile: str | None = None,
) -> dict[str, Any]:
    profile = str(fund_profile or "generalist").strip().lower().replace("-", "_")
    if profile not in FUND_PROFILE_WEIGHTS:
        profile = "generalist"
    company_slug = slugify(company)
    source_records, source_records_by_id = build_source_records(company, records, sources)
    evidence_items = build_evidence_items(company, records, sources, source_records_by_id)
    pre_claim_ids = {key: stable_short_id("claim", company_slug, key) for key in {canonical_claim_key(ev) for ev in evidence_items}}
    graph = build_evidence_graph(
        entity_id=company_slug,
        entity_label=company,
        source_records=source_records,
        evidence_items=evidence_items,
        claim_ids_by_key=pre_claim_ids,
        canonical_claim_key_resolver=canonical_claim_key,
        strengthening_edges=[
            ("traction.paid_customers", "traction.revenue.arr", 0.4),
            ("traction.pilots", "traction.pipeline", 0.4),
        ],
    )
    claim_records = aggregate_claim_records(
        entity_id=company_slug,
        evidence_items=evidence_items,
        graph=graph,
        canonical_claim_key_resolver=canonical_claim_key,
        value_extractor=extract_claim_value,
        required_next_evidence_resolver=required_next_evidence_for_claim,
        motion_resolver=motion_for_claim,
        self_reported_confidence_caps={"traction.": 60},
    )
    dimension_scores = {
        dimension: dimension_score_from_claims(claim_records, dimension, dimension_resolver=claim_dimension)
        for dimension in ("team", "market", "product", "traction", "moat", "financial", "risk")
    }
    dimension_scores["evidence_quality"] = score_evidence_quality(evidence_items, source_records)
    weights = fund_profile_weights(profile)
    raw_score = clamp_score(sum(dimension_scores[dimension] * weight for dimension, weight in weights.items())) if claim_records else None
    investment_score, score_caps = apply_company_score_caps(raw_score, claim_records, dimension_scores["evidence_quality"], profile)
    truth_discovery = build_truth_discovery_layer(company_slug, evidence_items, claim_records, source_records)
    bayesian_explanations = build_bayesian_explainability_layer(company, evidence_items, claim_records, source_records, truth_discovery)
    summary = CompanyEvidenceSummary(
        company_slug=company_slug,
        investment_score=investment_score,
        evidence_quality_score=dimension_scores["evidence_quality"],
        confidence_band=confidence_band(dimension_scores["evidence_quality"]),
        recommendation=recommendation_for_company(investment_score, dimension_scores["evidence_quality"], score_caps),
        dimension_scores=dimension_scores,
        score_caps=score_caps,
        claim_count=len(claim_records),
        evidence_count=len(evidence_items),
    )
    return {
        "fund_profile": profile,
        "source_records": source_records,
        "evidence_items": evidence_items,
        "claim_records": claim_records,
        "evidence_graph": graph,
        "company_evidence_summary": asdict(summary),
        "truth_discovery": truth_discovery,
        "bayesian_claim_explanations": bayesian_explanations,
    }


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
    results = run_scorers(scorers, facts, max_workers=worker_count)
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


def build_company_analysis(
    company: str,
    records: list[dict[str, Any]],
    research_ledger: dict[str, list[dict[str, Any]]],
    scoring_workers: int = 1,
    fund_profile: str | None = None,
) -> dict[str, Any]:
    sources = [source for stage_sources in research_ledger.values() for source in stage_sources]
    facts = build_fact_table(company, records, sources)
    methods = score_company_methods(facts, max_workers=scoring_workers)
    audit = audit_method_scores(methods, facts)
    scored = [item["score"] for item in methods.values() if isinstance(item.get("score"), (int, float))]
    missing_methods = [method_id for method_id, method in methods.items() if method["status"] == "insufficient_evidence"]
    substantive_sources = [source for source in sources if is_substantive_public_source(source)]
    evidence_layer = build_company_evidence_layer(company, records, sources, fund_profile=fund_profile)
    evidence_summary_layer = evidence_layer["company_evidence_summary"]
    composite_score = evidence_summary_layer["investment_score"]
    method_average_score = round(sum(scored) / len(scored), 2) if scored else None
    return {
        "company_name": company,
        "company_slug": slugify(company),
        "composite_score": composite_score,
        "investment_score": composite_score,
        "method_average_score": method_average_score,
        "evidence_quality_score": evidence_summary_layer["evidence_quality_score"],
        "confidence_band": evidence_summary_layer["confidence_band"],
        "recommendation": evidence_summary_layer["recommendation"],
        "dimension_scores": evidence_summary_layer["dimension_scores"],
        "score_caps": evidence_summary_layer["score_caps"],
        "fund_profile": evidence_layer["fund_profile"],
        "method_count": len(methods),
        "methods": methods,
        "method_score_appendix": methods,
        "source_records": evidence_layer["source_records"],
        "evidence_items": evidence_layer["evidence_items"],
        "claim_records": evidence_layer["claim_records"],
        "evidence_graph": evidence_layer["evidence_graph"],
        "company_evidence_summary": evidence_summary_layer,
        "truth_discovery": evidence_layer.get("truth_discovery", {}),
        "bayesian_claim_explanations": evidence_layer.get("bayesian_claim_explanations", []),
        "fact_table": facts,
        "audit": audit,
        "evidence_summary": {
            "document_count": len(records),
            "source_count": len(sources),
            "substantive_source_count": len(substantive_sources),
            "financial_tool_source_count": len([source for source in sources if source.get("skill") == "financial_public_data_tool"]),
            "missing_methods": missing_methods,
            "composite_score_evidence": {
                "status": "scored" if composite_score is not None else "insufficient_evidence",
                "scored_method_count": len(scored),
                "method_ids": [method_id for method_id, method in methods.items() if isinstance(method.get("score"), (int, float))],
                "reason": "Composite is the confidence-weighted investment score from normalized claims; method scores are retained as an appendix." if composite_score is not None else "No normalized claim evidence was available for a numeric score.",
                "method_average_score": method_average_score,
                "evidence_quality_score": evidence_summary_layer["evidence_quality_score"],
                "confidence_band": evidence_summary_layer["confidence_band"],
                "fund_profile": evidence_layer["fund_profile"],
                "truth_discovery_eligible_claim_count": len((evidence_layer.get("truth_discovery") or {}).get("eligible_claim_ids") or []),
                "bayesian_claim_explanation_count": len(evidence_layer.get("bayesian_claim_explanations") or []),
            },
        },
        "result_evidence": {
            "composite_score": {
                "value": composite_score,
                "why": "Confidence-weighted normalized claims by fund profile, with hard caps for missing team, traction, product, or evidence quality." if composite_score is not None else "No scored normalized claims were available.",
                "evidence_refs": sorted({ev.get("evidence_id") for ev in evidence_layer["evidence_items"] if ev.get("evidence_id")})[:20],
                "missing_evidence": dedupe_list(
                    [
                        missing
                        for claim in evidence_layer["claim_records"]
                        for missing in (claim.get("required_next_evidence") or [])[:2]
                        if int(claim.get("net_confidence") or 0) < 70
                    ],
                    20,
                ),
                "score_caps": evidence_summary_layer["score_caps"],
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


def summarize_local_evidence(records: list[dict[str, Any]], *, limit: int = 8) -> dict[str, Any]:
    readable_records = [
        record
        for record in records
        if int(record.get("character_count") or 0) > 0 and not record.get("ocr_required")
    ]
    return {
        "record_count": len(records),
        "readable_record_count": len(readable_records),
        "total_character_count": sum(int(record.get("character_count") or 0) for record in records),
        "files": [
            {
                "filename": record.get("filename"),
                "suffix": record.get("suffix"),
                "sha256_prefix": str(record.get("sha256") or "")[:12],
                "character_count": record.get("character_count"),
                "extraction_method": record.get("extraction_method"),
                "warning_count": len(record.get("warnings") or []),
            }
            for record in records[:limit]
        ],
    }


def summarize_research_sources(sources: list[dict[str, Any]], *, limit: int = 12) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for source in sources:
        status = str(source.get("status") or "unknown")
        quality = str(source.get("source_quality_label") or "thin_signal")
        target = str(source.get("verification_target") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        target_counts[target] = target_counts.get(target, 0) + 1
    substantive = [source for source in sources if is_substantive_public_source(source)]
    return {
        "source_count": len(sources),
        "substantive_source_count": len(substantive),
        "status_counts": status_counts,
        "source_quality_counts": quality_counts,
        "verification_target_counts": target_counts,
        "sample_sources": [
            {
                "title": source.get("title"),
                "url": source.get("url"),
                "status": source.get("status"),
                "source_quality_label": source.get("source_quality_label"),
                "verification_target": source.get("verification_target"),
                "warning": source.get("warning"),
            }
            for source in sources[:limit]
        ],
    }


def build_company_evidence_summaries(
    analyses: list[dict[str, Any]],
    company_records: dict[str, list[dict[str, Any]]],
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    summaries = []
    for analysis in analyses:
        company = analysis["company_name"]
        sources = flattened_sources(research_ledgers.get(company, {}))
        summaries.append(
            {
                "company_name": company,
                "company_slug": analysis["company_slug"],
                "investment_score": analysis.get("investment_score"),
                "evidence_quality_score": analysis.get("evidence_quality_score"),
                "confidence_band": analysis.get("confidence_band"),
                "recommendation": analysis.get("recommendation"),
                "claim_count": len(analysis.get("claim_records") or []),
                "normalized_evidence_count": len(analysis.get("evidence_items") or []),
                "local_evidence": summarize_local_evidence(company_records.get(company, []), limit=5),
                "research_sources": summarize_research_sources(sources, limit=8),
                "missing_methods": (analysis.get("evidence_summary") or {}).get("missing_methods", []),
            }
        )
    return summaries


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
    return shared_source_record(
        entity=company,
        query=query,
        url=url,
        title=title or url.split("//", 1)[-1].split("/", 1)[0],
        snippet=snippet[:snippet_limit],
        status=status,
        skill=skill,
        verification_target=verification_target,
        warning=warning,
        retrieved_at=utc_now_iso(),
        source_quality_label=quality if quality in SOURCE_QUALITY_LABELS else "thin_signal",
    )


def _mock_public_source(
    *,
    company: str,
    query: str,
    skill: str,
    verification_target: str,
    url: str = "",
    title: str = "",
) -> dict[str, Any]:
    source = _source_record(
        company=company,
        query=query,
        url=url or f"https://mock.local/{slugify(company)}/{slugify(verification_target)}",
        title=title or f"Mock {verification_target.replace('_', ' ')} source for {company}",
        snippet=(
            f"Mock source generated by --fake-skills for {company}. "
            "It simulates public evidence so the VC Assistant workflow can exercise downstream scoring and reporting quickly."
        ),
        status="mocked",
        skill=skill,
        verification_target=verification_target,
        warning="fake_skills mock source; do not use for investment decisions",
        source_quality_label="thin_signal",
    )
    source["mocked"] = True
    return source


def _budget_exhausted_source(company: str, query: str, skill: str, verification_target: str, action_type: str) -> dict[str, Any]:
    source = shared_budget_exhausted_source(company, query, skill, verification_target, action_type)
    source.update(
        {
            "url": "action_budget",
            "title": "Action budget exhausted",
            "snippet": f"Skipped {action_type} because the VC Assistant action budget was exhausted.",
            "warning": "Action budget exhausted before this evidence source could be collected.",
        }
    )
    return source


def _compact_text(value: Any, *, limit: int) -> str:
    text = redactor(str(value or "")).strip()
    compact = shared_compact_text(text, limit=limit)
    return compact if len(text) <= limit else compact.rstrip() + "...[truncated]"


def compact_local_evidence_for_transport(
    records: list[dict[str, Any]],
    *,
    limit: int = MAX_TRANSPORT_EVIDENCE_PER_COMPANY,
) -> list[dict[str, Any]]:
    compact_records = shared_compact_local_evidence_for_transport(
        records,
        limit=limit,
        text_limit=MAX_TRANSPORT_TEXT_PREVIEW_CHARS,
    )
    for item, record in zip(compact_records, records[:limit]):
        item.update(
            {
                "kind": "local_document_evidence",
                "suffix": record.get("suffix"),
                "sha256_prefix": str(record.get("sha256") or "")[:16],
                "extraction_method": record.get("extraction_method"),
                "ocr_required": bool(record.get("ocr_required")),
                "warnings": [_compact_text(warning, limit=240) for warning in (record.get("warnings") or [])[:5]],
            }
        )
    return compact_records


def compact_research_sources_for_transport(
    sources: list[dict[str, Any]],
    *,
    limit: int = MAX_TRANSPORT_SOURCES_PER_COMPANY,
) -> list[dict[str, Any]]:
    compact_sources = shared_compact_research_sources_for_transport(
        sources,
        limit=limit,
        snippet_limit=MAX_TRANSPORT_SNIPPET_CHARS,
    )
    for item, source in zip(compact_sources, sources[:limit]):
        item.update(
            {
                "company": source.get("company"),
                "query": _compact_text(source.get("query"), limit=360),
                "url": _compact_text(source.get("url"), limit=1000),
                "title": _compact_text(source.get("title"), limit=300),
                "warning": _compact_text(source.get("warning"), limit=500),
                "retrieved_at": source.get("retrieved_at"),
            }
        )
        for key in ("agent_id", "tool_call_id", "tool_decision_source", "fallback_after_agentic"):
            if source.get(key) is not None:
                item[key] = source.get(key)
    return compact_sources


def compact_company_report_for_transport(report: dict[str, Any]) -> dict[str, Any]:
    compact = {**shared_compact_company_report_for_transport(report), **dict(report)}
    evidence = report.get("evidence")
    if isinstance(evidence, list):
        compact["evidence"] = compact_local_evidence_for_transport(evidence)
    sources = report.get("research_sources")
    if isinstance(sources, list):
        compact["research_sources"] = compact_research_sources_for_transport(sources)
    return compact


def python_http_fallback_config(internet: dict[str, Any]) -> dict[str, Any]:
    raw = internet.get("python_http_fallback") if isinstance(internet.get("python_http_fallback"), dict) else {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "timeout_seconds": bounded_int(raw.get("timeout_seconds") or internet.get("timeout_seconds"), default=10, minimum=2, maximum=30),
        "max_chars": bounded_int(raw.get("max_chars") or internet.get("max_chars"), default=8000, minimum=1000, maximum=20000),
        "max_search_results": bounded_int(raw.get("max_search_results"), default=3, minimum=1, maximum=8),
        "user_agent": str(raw.get("user_agent") or "MirrorNeuron-VC-Assistant/1.0 (+public research fallback)"),
    }


def _html_to_text(html_text: str, *, limit: int) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html_text or "")
    value = re.sub(r"(?is)<!--.*?-->", " ", value)
    value = re.sub(r"(?is)<br\s*/?>", "\n", value)
    value = re.sub(r"(?is)</p\s*>", "\n", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    value = html_lib.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _html_title(html_text: str, fallback: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text or "")
    if match:
        title = _html_to_text(match.group(1), limit=300)
        if title:
            return title
    return fallback


def _fetch_public_http(url: str, *, internet: dict[str, Any]) -> dict[str, Any]:
    fallback = python_http_fallback_config(internet)
    if not fallback["enabled"]:
        return {"status": "disabled", "url": url, "title": url, "text": "", "error": "python_http_fallback disabled"}
    if not str(url or "").startswith(("http://", "https://")):
        return {"status": "failed", "url": url, "title": url, "text": "", "error": "public HTTP fallback requires an http(s) URL"}
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": fallback["user_agent"],
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
        },
    )
    raw = b""
    final_url = url
    content_type = ""
    status_code = 0
    try:
        with urllib.request.urlopen(request, timeout=float(fallback["timeout_seconds"])) as response:
            final_url = response.geturl() or url
            status_code = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("content-type") or "")
            raw = response.read(int(fallback["max_chars"]) * 4)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        final_url = exc.geturl() or url
        status_code = int(getattr(exc, "code", 0) or 0)
        content_type = str(exc.headers.get("content-type") or "") if exc.headers else ""
        raw = exc.read(min(int(fallback["max_chars"]) * 2, 12000))
        charset = exc.headers.get_content_charset() if exc.headers else None
        charset = charset or "utf-8"
    except Exception as exc:
        return {"status": "failed", "url": final_url, "title": host_from_url(final_url) or final_url, "text": "", "html": "", "error": str(exc), "http_status": status_code}
    decoded = raw.decode(charset or "utf-8", errors="replace")
    is_html = "html" in content_type.lower() or "<html" in decoded[:500].lower()
    text = _html_to_text(decoded, limit=int(fallback["max_chars"])) if is_html else decoded[: int(fallback["max_chars"])]
    title = _html_title(decoded, host_from_url(final_url) or final_url) if is_html else (host_from_url(final_url) or final_url)
    return {
        "status": "ok" if 200 <= status_code < 400 and text.strip() else "failed",
        "url": final_url,
        "title": title,
        "text": text,
        "html": decoded[: int(fallback["max_chars"]) * 2] if is_html else "",
        "error": "" if 200 <= status_code < 400 else f"HTTP {status_code}",
        "http_status": status_code,
    }


def _search_url_for_query(query: str, internet: dict[str, Any]) -> str:
    template = str(internet.get("search_url_template") or "https://duckduckgo.com/html/?q={query}")
    return template.format(query=quote_plus(query))


def _extract_public_search_links(html_text: str, *, base_url: str, limit: int) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    search_hosts = ("duckduckgo.com", "google.com", "bing.com", "search.yahoo.com")
    for match in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html_text or ""):
        href = html_lib.unescape(match.group(1)).strip()
        label = _html_to_text(match.group(2), limit=240)
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        parsed_href = urlparse(urljoin(base_url, href))
        query = parse_qs(parsed_href.query)
        if "uddg" in query and query["uddg"]:
            href = unquote(query["uddg"][0])
        elif href.startswith("//"):
            href = "https:" + href
        else:
            href = urljoin(base_url, href)
        if not href.startswith(("http://", "https://")):
            continue
        host = host_from_url(href).lower()
        if any(host == search_host or host.endswith("." + search_host) for search_host in search_hosts):
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append({"url": href, "title": label or host})
        if len(links) >= limit:
            break
    return links


def _append_python_http_search(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    verification_target: str,
    action_budget: ActionBudget | None = None,
) -> None:
    fallback = python_http_fallback_config(internet)
    if not fallback["enabled"]:
        return
    query = str((plan.get("queries") or [""])[0])
    search_url = _search_url_for_query(query, internet)
    action = action_budget.start(
        action_type="browser_search",
        stage=verification_target,
        company=company,
        tool="python_http_fallback.search",
        metadata={"query": query},
    ) if action_budget else None
    if action_budget and action is None:
        sources.append(_budget_exhausted_source(company, query, "python_http_fallback", verification_target, "browser_search"))
        return
    search_result = _fetch_public_http(search_url, internet=internet)
    if action_budget:
        action_budget.complete(action, str(search_result.get("status") or "failed"), {"url": search_result.get("url"), "http_status": search_result.get("http_status")})
    if search_result.get("status") != "ok":
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=search_url,
                title="Python HTTP search fallback failed",
                snippet=str(search_result.get("text") or search_result.get("error") or ""),
                status="failed",
                skill="python_http_fallback",
                verification_target=verification_target,
                warning=str(search_result.get("error") or "search fetch failed"),
            )
        )
        return
    links = _extract_public_search_links(
        str(search_result.get("html") or ""),
        base_url=str(search_result.get("url") or search_url),
        limit=int(fallback["max_search_results"]),
    )
    if not links:
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(search_result.get("url") or search_url),
                title=str(search_result.get("title") or "Search results"),
                snippet=str(search_result.get("text") or ""),
                status="ok",
                skill="python_http_fallback",
                verification_target=verification_target,
                source_quality_label="thin_signal",
                warning="Search page fetched but no public result links were extracted.",
            )
        )
        return
    for link in links:
        page_action = action_budget.start(
            action_type="browser_page",
            stage=verification_target,
            company=company,
            tool="python_http_fallback.fetch_result",
            metadata={"url": link["url"]},
        ) if action_budget else None
        if action_budget and page_action is None:
            sources.append(_budget_exhausted_source(company, query, "python_http_fallback", verification_target, "browser_page"))
            continue
        page = _fetch_public_http(link["url"], internet=internet)
        if action_budget:
            action_budget.complete(page_action, str(page.get("status") or "failed"), {"url": page.get("url"), "http_status": page.get("http_status")})
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(page.get("url") or link["url"]),
                title=str(page.get("title") or link.get("title") or ""),
                snippet=str(page.get("text") or page.get("error") or ""),
                status=str(page.get("status") or "failed"),
                skill="python_http_fallback",
                verification_target=verification_target,
                warning=str(page.get("error") or ""),
            )
        )


def _append_python_http_target_research(
    sources: list[dict[str, Any]],
    *,
    company: str,
    plan: dict[str, Any],
    internet: dict[str, Any],
    action_budget: ActionBudget | None = None,
) -> None:
    fallback = python_http_fallback_config(internet)
    if not fallback["enabled"]:
        return
    query = str((plan.get("queries") or [""])[0])
    for url in (plan.get("target_urls") or [])[: int(internet.get("max_target_urls_per_company") or 2)]:
        if not str(url).startswith(("http://", "https://")):
            continue
        target = "crunchbase" if "crunchbase.com" in str(url) else "public_profile"
        action = action_budget.start(
            action_type="browser_page",
            stage=target,
            company=company,
            tool="python_http_fallback.fetch_url",
            metadata={"url": url},
        ) if action_budget else None
        if action_budget and action is None:
            sources.append(_budget_exhausted_source(company, query, "python_http_fallback", target, "browser_page"))
            continue
        result = _fetch_public_http(str(url), internet=internet)
        if action_budget:
            action_budget.complete(action, str(result.get("status") or "failed"), {"url": result.get("url"), "http_status": result.get("http_status")})
        sources.append(
            _source_record(
                company=company,
                query=query,
                url=str(result.get("url") or url),
                title=str(result.get("title") or ""),
                snippet=str(result.get("text") or result.get("error") or ""),
                status=str(result.get("status") or "failed"),
                skill="python_http_fallback",
                verification_target=target,
                warning=str(result.get("error") or ""),
            )
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
        "enabled": bool(raw.get("enabled", False)),
        "agent_ids": [str(item) for item in (raw.get("agent_ids") or DEFAULT_AGENTIC_RESEARCH_AGENT_IDS)],
        "max_iterations_per_agent": bounded_int(raw.get("max_iterations_per_agent"), default=1, minimum=1, maximum=100),
        "max_tool_calls_per_agent": bounded_int(raw.get("max_tool_calls_per_agent"), default=2, minimum=0, maximum=500),
        "allowed_tools": [str(item) for item in (raw.get("allowed_tools") or DEFAULT_AGENTIC_RESEARCH_TOOLS)],
    }


def actor_review_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("actor_review") if isinstance(config.get("actor_review"), dict) else {}
    memory = config.get("memory_layer") if isinstance(config.get("memory_layer"), dict) else {}
    conversation = memory.get("conversation") if isinstance(memory.get("conversation"), dict) else {}
    selected = raw.get("llm_actor_ids") if isinstance(raw.get("llm_actor_ids"), list) else DEFAULT_ACTOR_REVIEW_LLM_ACTOR_IDS
    return {
        "llm_actor_ids": [str(item) for item in selected],
        "max_context_chars": bounded_int(raw.get("max_context_chars"), default=6000, minimum=2000, maximum=50000),
        "use_context_engine": bool(raw.get("use_context_engine", raw.get("use_model_compression", conversation.get("use_model_compression", True)))),
        "working_memory_persist_to_redis": bool(raw.get("working_memory_persist_to_redis", False)),
        "context_token_budget": bounded_int(raw.get("context_token_budget"), default=conversation.get("token_budget") or DEFAULT_ACTOR_REVIEW_CONTEXT_TOKEN_BUDGET, minimum=500, maximum=20000),
        "context_target_tokens": bounded_int(raw.get("context_target_tokens"), default=conversation.get("target_tokens") or DEFAULT_ACTOR_REVIEW_CONTEXT_TARGET_TOKENS, minimum=200, maximum=8000),
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
        warning=message if status in {"agent_tool_loop_failed", "agent_invalid_tool_call", "agent_tool_call_failed", "blocked"} else "",
        source_quality_label="blocked" if status in {"agent_tool_loop_failed", "agent_invalid_tool_call", "agent_tool_call_failed", "blocked"} else "thin_signal",
    )
    record["agent_id"] = agent_id
    record["tool_call_id"] = tool_call_id
    record["tool_decision_source"] = "llm_agent"
    return record


def _annotate_agent_sources(sources: list[dict[str, Any]], start_index: int, *, agent_id: str, tool_call_id: str) -> None:
    shared_annotate_agent_sources(sources, start_index, agent_id=agent_id, tool_call_id=tool_call_id)
    for source in sources[start_index:]:
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
    shared_error = shared_validate_agent_tool_call(tool_call, allowed_tools=allowed_tools, internet=internet)
    if shared_error:
        return shared_error
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
    observation = shared_observation_from_sources(sources, start_index)
    added = sources[start_index:]
    observation["statuses"] = sorted({str(source.get("status") or "") for source in added if source.get("status")})
    observation["urls"] = [str(source.get("url") or "") for source in added[:5]]
    observation["snippets"] = [str(source.get("snippet") or "")[:240] for source in added[:3]]
    return observation


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
    return {
        "status": "executed",
        **_agent_observation_from_sources(sources, start_index),
        "mocked": any(source.get("mocked") for source in sources[start_index:]),
    }


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
    return prompt_spec_from_markdown(RESEARCH_AGENT_PROMPT_FILES.get(agent_id, RESEARCH_AGENT_PROMPT_FILES["research_planner"]))


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
    system_prompt = load_prompt(
        "research-agent-system.md",
        agent_id=stage,
        mission=spec["mission"],
    )
    return system_prompt, {
        "task": load_prompt("research-agent-task.md"),
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


def build_research_stage_rag_query(*, stage: str, plan: dict[str, Any]) -> str:
    spec = research_prompt_spec(stage)
    stage_queries = (plan.get("stage_queries") or {}).get(stage, []) if isinstance(plan.get("stage_queries"), dict) else []
    if not stage_queries:
        stage_queries = plan.get("queries") or []
    lane_ids = [
        str(lane.get("lane_id") or "")
        for lane in plan.get("lanes", [])[:8]
        if isinstance(lane, dict) and lane.get("lane_id")
    ]
    parts = [
        stage,
        spec["mission"],
        " ".join(spec["rag_query_terms"]),
        " ".join(lane_ids),
        " ".join(str(query) for query in stage_queries[:3]),
    ]
    return " ".join(part for part in parts if part).strip()


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
    rag_query = build_research_stage_rag_query(stage=stage, plan=plan)
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
                try:
                    result = _execute_agent_tool_call(sources=sources, company=company, stage=stage, plan=plan, internet=internet, run_dir=run_dir, action_budget=action_budget, tool_call=tool_call, tool_call_id=tool_call_id)
                except Exception as exc:
                    result = {"status": "failed", "source_count": 0, "error": str(exc)}
                    sources.append(
                        _agent_tool_source(
                            company=company,
                            agent_id=stage,
                            query=str(tool_call.get("query") or ""),
                            status="agent_tool_call_failed",
                            message=str(exc),
                            tool_call_id=tool_call_id,
                        )
                    )
                op.close(
                    "completed" if result.get("status") in {"executed", "finished"} else "failed",
                    tool_status=result.get("status"),
                    source_count=result.get("source_count"),
                    error=result.get("error"),
                    mocked=bool(result.get("mocked")),
                )
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
    source_count_start = len(sources)
    tool_status = "completed"
    tool_error = ""
    op = observed_operation(
        run_dir,
        phase="public_tool_call",
        operation="w3m_browser_skill.research_topic",
        tool="w3m_browser_skill.research_topic",
        company=company,
        verification_target=verification_target,
        query_hash=stable_text_hash((plan.get("queries") or [""])[0]),
        query_chars=len(str((plan.get("queries") or [""])[0])),
    ).__enter__()
    try:
        _append_w3m_research_unobserved(
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


def _append_w3m_research_unobserved(
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
                skill="w3m_browser_skill.research_topic",
                verification_target=verification_target,
            )
        )
        append_observation_record(
            run_dir,
            "skill_mock_used",
            {
                "phase": "public_tool_call",
                "operation": "w3m_browser_skill.research_topic",
                "tool": "w3m_browser_skill.research_topic",
                "status": "mocked",
                "company": company,
                "mocked": True,
                "source_count": 1,
            },
        )
        return
    _load_w3m_browser_skill()
    query = plan["queries"][0]
    max_sources = int(internet.get("max_sources_per_company") or 3)
    if W3mBrowserConfig is None or research_topic is None or browse_url is None:
        _append_python_http_search(
            sources,
            company=company,
            plan=plan,
            internet=internet,
            verification_target=verification_target,
            action_budget=action_budget,
        )
        if not any(source.get("skill") == "python_http_fallback" for source in sources):
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
        _append_python_http_search(
            sources,
            company=company,
            plan=plan,
            internet=internet,
            verification_target=verification_target,
            action_budget=action_budget,
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
    source_count_start = len(sources)
    tool_status = "completed"
    tool_error = ""
    target_urls = plan.get("target_urls") or []
    op = observed_operation(
        run_dir,
        phase="public_tool_call",
        operation="w3m_browser_skill.browse_url",
        tool="w3m_browser_skill.browse_url",
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
                    skill="w3m_browser_skill.browse_url",
                    verification_target="public_profile",
                )
            )
        append_observation_record(
            run_dir,
            "skill_mock_used",
            {
                "phase": "public_tool_call",
                "operation": "w3m_browser_skill.browse_url",
                "tool": "w3m_browser_skill.browse_url",
                "status": "mocked",
                "company": company,
                "mocked": True,
                "source_count": len(urls[: int(internet.get("max_target_urls_per_company") or 2)]),
            },
        )
        return
    _load_w3m_browser_skill()
    if W3mBrowserConfig is None or browse_url is None:
        before_fallback = len(sources)
        _append_python_http_target_research(
            sources,
            company=company,
            plan=plan,
            internet=internet,
            action_budget=action_budget,
        )
        if len(sources) == before_fallback:
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
            fallback_action = action_budget.start(
                action_type="browser_page",
                stage=target,
                company=company,
                tool="python_http_fallback.fetch_url",
                metadata={"url": url, "fallback_reason": str(exc)[:240]},
            ) if action_budget else None
            if not action_budget or fallback_action is not None:
                fallback_result = _fetch_public_http(str(url), internet=internet)
                if action_budget:
                    action_budget.complete(
                        fallback_action,
                        str(fallback_result.get("status") or "failed"),
                        {"url": fallback_result.get("url"), "http_status": fallback_result.get("http_status")},
                    )
                sources.append(
                    _source_record(
                        company=company,
                        query=plan["queries"][0],
                        url=str(fallback_result.get("url") or url),
                        title=str(fallback_result.get("title") or ""),
                        snippet=str(fallback_result.get("text") or fallback_result.get("error") or ""),
                        status=str(fallback_result.get("status") or "failed"),
                        skill="python_http_fallback",
                        verification_target=target,
                        warning=str(fallback_result.get("error") or ""),
                    )
                )
                continue
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
        operation="web_browser_skill.scrape_page",
        tool="web_browser_skill.scrape_page",
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
                    skill="web_browser_skill.scrape_page",
                    verification_target="rendered_public_profile",
                )
            )
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
        call_with_supported_kwargs(_append_rendered_browser_research, sources=sources, company=company, plan=stage_plan, internet=internet, run_dir=run_dir, action_budget=action_budget)
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


def _stage_needs_deterministic_gap_fill(sources: list[dict[str, Any]]) -> bool:
    if any(is_substantive_public_source(source) for source in sources):
        return False
    return any(str(source.get("status") or "") in {"planned", "warning", "failed", "blocked", "skill_unavailable", "agent_tool_loop_failed", "agent_invalid_tool_call"} for source in sources)


def _with_agentic_gap_fill(
    *,
    company: str,
    stage: str,
    sources: list[dict[str, Any]],
    query: str | list[str],
    plan: dict[str, Any],
    internet: dict[str, Any],
    run_dir: Path | None,
    action_budget: ActionBudget | None,
) -> tuple[str, list[dict[str, Any]]]:
    if not _stage_needs_deterministic_gap_fill(sources):
        return stage, sources
    _, fallback_sources = _research_one_stage(company, stage, query, plan, internet, run_dir, action_budget)
    for source in fallback_sources:
        source["fallback_after_agentic"] = True
    return stage, [*sources, *fallback_sources]


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
    normalized_results = []
    for stage, stage_sources in results:
        if llm is not None and _agent_stage_enabled(agentic, stage):
            normalized_results.append(
                _with_agentic_gap_fill(
                    company=company,
                    stage=stage,
                    sources=stage_sources,
                    query=staged_queries.get(stage, []),
                    plan=plan,
                    internet=internet,
                    run_dir=run_dir,
                    action_budget=action_budget,
                )
            )
        else:
            normalized_results.append((stage, stage_sources))
    results = normalized_results
    by_stage = {stage: sources for stage, sources in results}
    if planner_sources:
        by_stage["company_identity_researcher"] = planner_sources + by_stage.get("company_identity_researcher", [])
    return {stage: by_stage.get(stage, []) for stage in RESEARCH_STAGE_IDS}


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


def render_markdown(analysis: dict[str, Any], sources: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    claims = list(analysis.get("claim_records") or [])
    evidence_items = {str(item.get("evidence_id")): item for item in (analysis.get("evidence_items") or [])}
    positive_claims = sorted(
        [claim for claim in claims if float(claim.get("motion_strength") or 0) > 0],
        key=lambda item: (float(item.get("weighted_motion") or 0), int(item.get("importance") or 0)),
        reverse=True,
    )[:5]
    negative_claims = sorted(
        [claim for claim in claims if float(claim.get("motion_strength") or 0) < 0],
        key=lambda item: (abs(float(item.get("weighted_motion") or 0)), int(item.get("importance") or 0)),
        reverse=True,
    )[:5]
    evidence_rows = sorted(
        claims,
        key=lambda item: (int(item.get("importance") or 0), int(item.get("net_confidence") or 0)),
        reverse=True,
    )[:8]
    cap_reasons = [str(item.get("reason") or "") for item in (analysis.get("score_caps") or []) if item.get("reason")]
    missing_evidence = dedupe_list(
        [
            missing
            for claim in claims
            for missing in (claim.get("required_next_evidence") or [])[:3]
            if int(claim.get("net_confidence") or 0) < 70
        ],
        10,
    )
    lines = [
        f"# {analysis['company_name']} VC Heuristic Report",
        "",
        "This is a score-only early screening report with evidence-grounded claims. It separates investment attractiveness, evidence confidence, and diligence priority; it does not issue an investment decision.",
        "",
        f"Verdict: {str(analysis.get('recommendation') or 'needs_review').replace('_', ' ')}",
        f"Investment score: {analysis.get('investment_score') if analysis.get('investment_score') is not None else 'insufficient evidence'} / 100",
        f"Evidence quality: {analysis.get('evidence_quality_score', 0)} / 100",
        f"Confidence: {str(analysis.get('confidence_band') or 'not_reliable').replace('_', ' ')}",
        f"Fund profile: {analysis.get('fund_profile', 'generalist')}",
        "",
        "## Why This Is Interesting",
    ]
    if positive_claims:
        for claim in positive_claims:
            lines.append(f"- {claim.get('canonical_claim')} (confidence {claim.get('net_confidence')}%, importance {claim.get('importance')})")
    else:
        lines.append("- No positive investor-relevant claim was supported strongly enough to summarize.")
    lines += ["", "## Main Concerns"]
    if negative_claims:
        for claim in negative_claims:
            lines.append(f"- {claim.get('canonical_claim')} (confidence {claim.get('net_confidence')}%, importance {claim.get('importance')})")
    else:
        lines.append("- No explicit negative claim was found; this does not remove the need for diligence.")
    if cap_reasons:
        lines += ["", "## Score Caps"]
        for reason in cap_reasons:
            lines.append(f"- {reason}")
    lines += ["", "## Dimension Scores"]
    for dimension, score in (analysis.get("dimension_scores") or {}).items():
        lines.append(f"- {dimension}: {score}")
    lines += [
        "",
        "## Most Important Claims",
        "| Claim | Direction | Confidence | Importance | Evidence |",
        "|---|---:|---:|---:|---|",
    ]
    if evidence_rows:
        for claim in evidence_rows:
            refs = []
            for evidence_id in claim.get("evidence_ids") or []:
                item = evidence_items.get(str(evidence_id)) or {}
                refs.append(str(item.get("filename") or item.get("source_url") or evidence_id))
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(claim.get("canonical_claim")),
                        markdown_cell(claim.get("motion_direction")),
                        markdown_cell(claim.get("net_confidence")),
                        markdown_cell(claim.get("importance")),
                        markdown_cell(", ".join(dedupe_list(refs, 3))),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| No normalized claims found | neutral | 0 | 0 | none |")
    truth_discovery = analysis.get("truth_discovery") or {}
    truth_rows = list(truth_discovery.get("claim_truth_scores") or [])[:8]
    reliability_rows = sorted(
        list(truth_discovery.get("source_reliability") or []),
        key=lambda item: float(item.get("combined_reliability") or item.get("prior_reliability") or 0),
        reverse=True,
    )[:8]
    lines += ["", "## Truth Discovery"]
    for note in truth_discovery.get("notes") or ["Truth discovery was not available for this run."]:
        lines.append(f"- {note}")
    if truth_rows:
        lines += [
            "",
            "| Claim | Log-Odds Probability | Crowd-Kit Probability | Final Truth Probability | Notes |",
            "|---|---:|---:|---:|---|",
        ]
        for row in truth_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(row.get("claim")),
                        markdown_cell(row.get("log_odds_probability")),
                        markdown_cell(row.get("crowdkit_probability") if row.get("crowdkit_probability") is not None else "n/a"),
                        markdown_cell(row.get("final_truth_probability")),
                        markdown_cell(row.get("note")),
                    ]
                )
                + " |"
            )
    if reliability_rows:
        lines += [
            "",
            "| Source | Source Type | Prior Reliability | Truth-Discovery Reliability | Combined Reliability |",
            "|---|---|---:|---:|---:|",
        ]
        for row in reliability_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(row.get("source_id")),
                        markdown_cell(row.get("source_type")),
                        markdown_cell(round(float(row.get("prior_reliability") or 0), 3)),
                        markdown_cell(round(float(row.get("truth_discovery_reliability")), 3) if row.get("truth_discovery_reliability") is not None else "n/a"),
                        markdown_cell(round(float(row.get("combined_reliability") or 0), 3)),
                    ]
                )
                + " |"
            )
    bayesian_explanations = list(analysis.get("bayesian_claim_explanations") or [])
    if bayesian_explanations:
        lines += ["", "## Bayesian Claim Explanation"]
        for explanation in bayesian_explanations:
            if explanation.get("status") == "failed":
                lines.append(f"- {markdown_cell(explanation.get('message') or explanation.get('warning'))}")
                continue
            markdown = str(explanation.get("markdown") or "").strip()
            if markdown:
                lines.append(markdown)
            else:
                lines += [
                    f"### {markdown_cell(explanation.get('canonical_claim') or explanation.get('claim_type'))}",
                    f"- Prior probability: {round(float(explanation.get('prior_probability') or 0) * 100)}%",
                    f"- Posterior probability: {round(float(explanation.get('posterior_probability') or 0) * 100)}%",
                    f"- Main confidence limiter: {markdown_cell(explanation.get('main_confidence_limiter') or 'none')}",
                    f"- Investor interpretation: {markdown_cell(explanation.get('investor_interpretation') or 'Structured belief update only.')}",
                ]
    lines += ["", "## Required Diligence"]
    if missing_evidence:
        for idx, item in enumerate(missing_evidence, start=1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("1. Review primary evidence and customer references before making any investment decision.")
    lines += [
        "",
        "## Method Score Appendix",
        f"- Method average score: {analysis.get('method_average_score') if analysis.get('method_average_score') is not None else 'insufficient_evidence'}",
        "",
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
        f"- Investment score basis: {composite_evidence.get('why', 'not recorded')}",
        f"- Scored methods: {analysis.get('evidence_summary', {}).get('composite_score_evidence', {}).get('scored_method_count', 0)}",
        f"- Missing method evidence: {', '.join(analysis.get('evidence_summary', {}).get('missing_methods', [])) or 'none'}",
        "",
        "## Evidence",
        f"- Local documents: {len(evidence)}",
        f"- Public sources: {len(sources)}",
        f"- Normalized evidence items: {len(analysis.get('evidence_items') or [])}",
        f"- Normalized claims: {len(claims)}",
        "",
    ]
    for item in evidence[:8]:
        lines.append(f"- {item['filename']}: {item.get('extraction_method')} ({item.get('sha256', '')[:12]})")
    lines += ["", "## Public Sources"]
    for source in sources:
        lines.append(f"- {source['title']}: {source['url']} ({source.get('source_quality_label', 'thin_signal')})")
    lines += ["", "## Research Gaps And Follow-Ups"]
    for item in research_gap_followups(analysis, sources):
        lines.append(f"- {item}")
    lines += ["", "## User Decision Boundary", "Use the claims, confidence scores, assumptions, and source refs to decide what to review next."]
    return "\n".join(lines) + "\n"


def build_research_coverage(research_ledgers: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    coverage = shared_build_research_coverage(research_ledgers)
    for company in coverage.get("companies", []):
        name = str(company.get("company_name") or "")
        ledger = research_ledgers.get(name) if isinstance(research_ledgers.get(name), dict) else {}
        company["company_slug"] = slugify(name)
        company["stage_counts"] = {stage: len(sources) for stage, sources in ledger.items()}
        company["statuses"] = sorted({str(source.get("status") or "") for sources in ledger.values() for source in sources if source.get("status")})
    coverage["generated_at"] = utc_now_iso()
    return coverage


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


def quality_check(status: str, message: str, **metadata: Any) -> dict[str, Any]:
    return shared_quality_check(status=status, message=message, **metadata)


def build_artifact_quality_report(
    *,
    analyses: list[dict[str, Any]],
    company_records: dict[str, list[dict[str, Any]]],
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
    output_files: list[dict[str, Any]],
    knowledge_rag: dict[str, Any] | None,
    actor_findings: dict[str, Any],
    actor_review_settings: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether every generated report has auditable evidence and source attempts."""
    files_by_company: dict[str, set[str]] = {}
    for item in output_files:
        company = str(item.get("company") or "")
        path = Path(str(item.get("path") or ""))
        if company and path.name:
            files_by_company.setdefault(company, set()).add(path.name)
    required_files = {"analysis.json", "analysis.md", "method_scores.json", "research_plan.json", "research_sources.json", "evidence.json", "warnings.json"}
    selected_actor_ids = set(actor_review_settings.get("llm_actor_ids") or [])
    actor_reviewed = {
        actor_id
        for actor_id in selected_actor_ids
        if isinstance(actor_findings.get(actor_id), dict) and actor_findings[actor_id].get("status") != "not_llm_reviewed"
    }
    rag_required = knowledge_rag_is_required(knowledge_rag or {})
    rag_ready = public_knowledge_rag_state(knowledge_rag or {}).get("status") in {"ready", "disabled"}
    companies: list[dict[str, Any]] = []
    total_warning_count = 0
    total_failed_count = 0
    for analysis in analyses:
        company = analysis["company_name"]
        records = company_records.get(company, [])
        ledger = research_ledgers.get(company, {})
        sources = flattened_sources(ledger)
        substantive_sources = [source for source in sources if is_substantive_public_source(source)]
        public_tool_attempts = [
            source
            for source in sources
            if source.get("skill") in {"w3m_browser_skill", "web_browser_skill", "financial_public_data_tool"}
            or str(source.get("url") or "").startswith("financial_tool://")
        ]
        failed_tool_attempts = [source for source in public_tool_attempts if source.get("status") in WARNING_SOURCE_STATUSES]
        financial_sources = [
            source
            for source in sources
            if source.get("skill") == "financial_public_data_tool" or str(source.get("url") or "").startswith("financial_tool://")
        ]
        missing_files = sorted(required_files - files_by_company.get(company, set()))
        method_missing_count = len(analysis.get("evidence_summary", {}).get("missing_methods") or [])
        checks = {
            "local_evidence": quality_check(
                "passed" if records else "warning",
                "Local startup packet evidence was captured." if records else "No local startup packet evidence was available for this company.",
                record_count=len(records),
            ),
            "public_research": quality_check(
                "passed" if substantive_sources else ("warning" if public_tool_attempts else "warning"),
                "Substantive public research sources were captured." if substantive_sources else "Public research has only failed, configured, planned, or thin-source records.",
                source_count=len(sources),
                substantive_source_count=len(substantive_sources),
                public_tool_attempt_count=len(public_tool_attempts),
                failed_tool_attempt_count=len(failed_tool_attempts),
            ),
            "financial_tool": quality_check(
                "passed" if financial_sources else "warning",
                "Deterministic financial comparable tool output is present." if financial_sources else "Deterministic financial comparable tool output is missing.",
                source_count=len(financial_sources),
            ),
            "method_evidence": quality_check(
                "passed" if method_missing_count == 0 else "warning",
                "All VC methods had enough evidence to score." if method_missing_count == 0 else "One or more VC methods are marked insufficient evidence.",
                missing_method_count=method_missing_count,
                missing_methods=analysis.get("evidence_summary", {}).get("missing_methods") or [],
            ),
            "rag_knowledge": quality_check(
                "passed" if rag_ready else ("failed" if rag_required else "warning"),
                "Required RAG knowledge was ready or disabled by config." if rag_ready else "RAG knowledge was not ready.",
                required=rag_required,
                rag_status=public_knowledge_rag_state(knowledge_rag or {}).get("status"),
            ),
            "actor_review": quality_check(
                "passed" if selected_actor_ids <= actor_reviewed else "warning",
                "Selected LLM actor reviewers produced findings." if selected_actor_ids <= actor_reviewed else "Some selected LLM actor reviewers did not produce live findings.",
                selected_actor_ids=sorted(selected_actor_ids),
                reviewed_actor_ids=sorted(actor_reviewed),
            ),
            "output_files": quality_check(
                "passed" if not missing_files else "failed",
                "Required per-company report files were written." if not missing_files else "Required per-company report files are missing.",
                missing_files=missing_files,
            ),
        }
        status_values = [item["status"] for item in checks.values()]
        company_status = "failed" if "failed" in status_values else ("warning" if "warning" in status_values else "passed")
        total_warning_count += status_values.count("warning")
        total_failed_count += status_values.count("failed")
        companies.append({
            "company_name": company,
            "company_slug": analysis["company_slug"],
            "status": company_status,
            "checks": checks,
            "summary": {
                "local_evidence_count": len(records),
                "research_source_count": len(sources),
                "substantive_source_count": len(substantive_sources),
                "public_tool_attempt_count": len(public_tool_attempts),
                "failed_tool_attempt_count": len(failed_tool_attempts),
                "financial_tool_source_count": len(financial_sources),
                "missing_method_count": method_missing_count,
            },
        })
    statuses = [company["status"] for company in companies]
    overall_status = "failed" if "failed" in statuses else ("warning" if "warning" in statuses else "passed")
    return {
        "generated_at": utc_now_iso(),
        "status": overall_status,
        "passes_required_gate": overall_status != "failed",
        "privacy": "metadata_only_no_raw_prompts_no_raw_public_pages_no_document_text",
        "company_count": len(companies),
        "warning_check_count": total_warning_count,
        "failed_check_count": total_failed_count,
        "companies": companies,
    }


def research_source_status_counts(research_ledgers: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ledger in research_ledgers.values():
        for source in flattened_sources(ledger):
            status = str(source.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    return counts


def build_run_health_report(
    *,
    run_id: str,
    started_at: str,
    elapsed_ms: float,
    artifact_quality: dict[str, Any],
    observation_summary: dict[str, Any],
    action_ledger: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
    cache_policy_summary: dict[str, Any],
    actor_review_warnings: list[dict[str, Any]],
    actor_review_settings: dict[str, Any],
    llm_limiter: LlmCallLimiter,
) -> dict[str, Any]:
    source_status_counts = research_source_status_counts(research_ledgers)
    warning_source_count = sum(count for status, count in source_status_counts.items() if status in WARNING_SOURCE_STATUSES)
    failed_operation_count = int(observation_summary.get("failed_operation_count") or 0)
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not artifact_quality.get("passes_required_gate"):
        failures.append({"kind": "artifact_quality", "message": "Artifact quality gate failed."})
    elif artifact_quality.get("status") == "warning":
        warnings.append({"kind": "artifact_quality", "message": "Artifact quality completed with warnings."})
    if action_ledger.get("exhausted"):
        warnings.append({"kind": "action_budget", "message": "Action budget was exhausted before all optional calls could run."})
    if warning_source_count:
        warnings.append({"kind": "public_tools", "message": "One or more public tool/source attempts returned warning or failed statuses.", "count": warning_source_count})
    if failed_operation_count:
        warnings.append({"kind": "observability", "message": "Observed operations include failed metadata records.", "count": failed_operation_count})
    if actor_review_warnings:
        warnings.append({"kind": "actor_review", "message": "Actor review completed with warnings.", "count": len(actor_review_warnings)})
    rag_state = public_knowledge_rag_state(knowledge_rag or {})
    if knowledge_rag_is_required(knowledge_rag or {}) and rag_state.get("status") not in {"ready"}:
        failures.append({"kind": "knowledge_rag", "message": "Required RAG knowledge is not ready.", "status": rag_state.get("status")})
    status = "failed" if failures else ("warning" if warnings else "healthy")
    return {
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "started_at": started_at,
        "elapsed_ms": round(elapsed_ms, 2),
        "status": status,
        "warnings": warnings,
        "failures": failures,
        "components": {
            "artifact_quality": {
                "status": artifact_quality.get("status"),
                "passes_required_gate": artifact_quality.get("passes_required_gate"),
                "warning_check_count": artifact_quality.get("warning_check_count"),
                "failed_check_count": artifact_quality.get("failed_check_count"),
            },
            "action_budget": {
                "budget": action_ledger.get("budget"),
                "used": action_ledger.get("used"),
                "remaining": action_ledger.get("remaining"),
                "exhausted": action_ledger.get("exhausted"),
            },
            "knowledge_rag": {
                "status": rag_state.get("status"),
                "required": knowledge_rag_is_required(knowledge_rag or {}),
                "indexed_count": (rag_state.get("index_summary") or {}).get("indexed_count") if isinstance(rag_state.get("index_summary"), dict) else None,
            },
            "public_tools": {
                "source_status_counts": source_status_counts,
                "warning_source_count": warning_source_count,
                "tool_operation_count": observation_summary.get("tool_operation_count"),
                "failed_operation_count": failed_operation_count,
            },
            "llm": {
                "llm_call_count": observation_summary.get("llm_call_count"),
                "limiter": llm_limiter.config_summary(),
            },
            "context_engine": {
                "actor_review_uses_context_engine": bool(actor_review_settings.get("use_context_engine")),
                "working_memory_persist_to_redis": bool(actor_review_settings.get("working_memory_persist_to_redis")),
                "boundary": "RAG knowledge may use Redis; working memory stays in local artifacts and compact prompt context.",
            },
            "cache_policy": {
                "force_reprocess": cache_policy_summary.get("force_reprocess"),
                "processed_company_count": cache_policy_summary.get("processed_company_count"),
                "skipped_company_count": cache_policy_summary.get("skipped_company_count"),
                "fresh_run": cache_policy_summary.get("fresh_run"),
            },
            "observability": {
                "trace_available": observation_summary.get("trace_available"),
                "record_count": observation_summary.get("record_count"),
                "failed_operation_count": failed_operation_count,
                "operation_counts": observation_summary.get("operation_counts"),
            },
        },
        "privacy": "metadata_only_no_prompts_no_raw_rag_context_no_document_text_no_raw_public_pages",
    }


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
    max_context_chars: int = 6000,
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


def _context_engine_summary(state: dict[str, Any], max_chars: int) -> dict[str, Any]:
    summary_keys = {
        "summary",
        "compiled",
        "compiled_context",
        "context",
        "compressed",
        "compressed_context",
        "messages",
        "items",
        "facts",
    }
    if not isinstance(state, dict):
        return {"compiled_context": _truncate_for_prompt(state, max_chars)}
    selected = {key: value for key, value in state.items() if key in summary_keys}
    if not selected:
        selected = dict(state)
    return _truncate_for_prompt(selected, max_chars)


def _local_context_engine_state(context: dict[str, Any], *, run_id: str, max_context_chars: int) -> dict[str, Any]:
    if WorkingMemory is None or MemoryItem is None:
        raise RuntimeError("mn_context_engine_sdk local WorkingMemory helpers are unavailable")
    focus_id = f"{run_id}_vc_actor_review"
    payload = {
        "decision_boundary": context.get("decision_boundary"),
        "company_count": context.get("company_count"),
        "processed_company_names": context.get("processed_company_names", []),
        "skipped_company_names": context.get("skipped_company_names", []),
        "company_summaries": context.get("company_summaries", []),
        "method_coverage": context.get("method_coverage", {}),
        "rag_context": {
            "enabled": (context.get("rag_context") or {}).get("enabled") if isinstance(context.get("rag_context"), dict) else None,
            "status": (context.get("rag_context") or {}).get("status") if isinstance(context.get("rag_context"), dict) else None,
            "citation_count": len((context.get("rag_context") or {}).get("citations") or []) if isinstance(context.get("rag_context"), dict) else 0,
            "citations": ((context.get("rag_context") or {}).get("citations") or [])[:5] if isinstance(context.get("rag_context"), dict) else [],
        },
        "output_files": (context.get("output_files") or [])[:10],
        "privacy_controls": context.get("privacy_controls", {}),
        "actor_review_focus": context.get("actor_review_focus", [])[:2],
    }
    payload = _truncate_for_prompt(payload, max_context_chars)
    memory = WorkingMemory()
    item = MemoryItem(
        type="Fact",
        status="validated",
        source=BLUEPRINT_ID,
        confidence=0.82,
        content={
            "goal_id": focus_id,
            "artifact_type": "vc_actor_review_context",
            "payload": payload,
            "source_refs": [
                item.get("path")
                for item in context.get("output_files", [])
                if isinstance(item, dict) and item.get("path")
            ],
            "validation": {
                "review_only": True,
                "private_document_text_included": False,
                "persistent_storage": False,
            },
        },
    )
    memory.add(item)
    return {
        "backend": "mn_context_engine_sdk.WorkingMemory",
        "storage": "in_process_only",
        "persisted": False,
        "item_count": len(memory.to_dict().get("items") or []),
        "compiled_context": _truncate_for_prompt(payload, max_context_chars),
    }


def _bounded_actor_prompt_context(context: dict[str, Any], *, compression: dict[str, Any], max_context_chars: int) -> dict[str, Any]:
    rag_context = context.get("rag_context") if isinstance(context.get("rag_context"), dict) else {}
    compressed_state = compression.get("state") if isinstance(compression.get("state"), dict) else {}
    prompt_context = {
        "blueprint_id": BLUEPRINT_ID,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "decision_boundary": context.get("decision_boundary"),
        "company_count": context.get("company_count"),
        "processed_company_names": context.get("processed_company_names", []),
        "skipped_company_names": context.get("skipped_company_names", []),
        "company_summaries": context.get("company_summaries", []),
        "method_coverage": context.get("method_coverage", {}),
        "rag_context": {
            "enabled": rag_context.get("enabled"),
            "status": rag_context.get("status"),
            "citation_count": len(rag_context.get("citations") or []),
            "citations": (rag_context.get("citations") or [])[:5],
        },
        "output_files": (context.get("output_files") or [])[:10],
        "privacy_controls": context.get("privacy_controls", {}),
        "actor_review_focus": context.get("actor_review_focus", [])[:2],
        "context_compression": {
            key: value
            for key, value in compression.items()
            if key not in {"state"}
        },
        "memory_boundary": {
            "rag_knowledge": "persistent Redis-backed knowledge index",
            "working_memory": "transient local prompt context; not written to Redis",
        },
    }
    if compressed_state:
        prompt_context["context_engine_summary"] = _context_engine_summary(compressed_state, max(1000, max_context_chars // 2))
        prompt_context["company_summaries"] = (prompt_context["company_summaries"] or [])[:5]
        prompt_context["method_coverage"] = _truncate_for_prompt(prompt_context["method_coverage"], max(800, max_context_chars // 6))
    encoded = json.dumps(prompt_context, default=str, ensure_ascii=False)
    if len(encoded) > max_context_chars:
        prompt_context["company_summaries"] = [
            {
                "company_name": item.get("company_name"),
                "company_slug": item.get("company_slug"),
                "processing_status": item.get("processing_status"),
                "composite_score": item.get("composite_score"),
                "missing_methods": item.get("missing_methods"),
                "audit_warning_count": item.get("audit_warning_count"),
            }
            for item in (prompt_context.get("company_summaries") or [])[:5]
            if isinstance(item, dict)
        ]
        prompt_context["method_coverage"] = _truncate_for_prompt(prompt_context.get("method_coverage", {}), 500)
        prompt_context["output_files"] = (prompt_context.get("output_files") or [])[:5]
        prompt_context["actor_review_focus"] = (prompt_context.get("actor_review_focus") or [])[:1]
    encoded = json.dumps(prompt_context, default=str, ensure_ascii=False)
    if len(encoded) > max_context_chars:
        prompt_context["context_engine_summary"] = _truncate_for_prompt(prompt_context.get("context_engine_summary", {}), max(600, max_context_chars // 3))
    prompt_context["context_json_chars"] = len(json.dumps(prompt_context, default=str, ensure_ascii=False))
    return prompt_context


def prepare_actor_review_prompt_context(
    *,
    run_id: str,
    context: dict[str, Any],
    config: dict[str, Any],
    run_dir: Path | None = None,
) -> dict[str, Any]:
    settings = actor_review_config(config)
    max_context_chars = int(settings["max_context_chars"])
    input_chars = len(json.dumps(context, default=str, ensure_ascii=False))
    compression: dict[str, Any] = {
        "enabled": False,
        "use_context_engine": bool(settings["use_context_engine"]),
        "working_memory_persist_to_redis": bool(settings["working_memory_persist_to_redis"]),
        "working_memory_storage": "local_prompt_only",
        "input_context_chars": input_chars,
        "token_budget": settings["context_token_budget"],
        "target_tokens": settings["context_target_tokens"],
    }
    if settings["working_memory_persist_to_redis"]:
        compression["warning"] = "working_memory_persist_to_redis=true is not supported for VC Assistant; using transient local working memory."
    if not settings["use_context_engine"]:
        compression["reason"] = "disabled"
        return _bounded_actor_prompt_context(context, compression=compression, max_context_chars=max_context_chars)
    with observed_operation(
        run_dir,
        phase="context_engine",
        operation="compile_actor_review_context",
        input_context_chars=input_chars,
        token_budget=settings["context_token_budget"],
        target_tokens=settings["context_target_tokens"],
    ) as op:
        try:
            state = _local_context_engine_state(context, run_id=run_id, max_context_chars=max_context_chars)
            compression.update({
                "enabled": True,
                "state": state if isinstance(state, dict) else {"compiled_context": state},
                "backend": "mn_context_engine_sdk.WorkingMemory",
                "persisted": False,
                "working_memory_storage": "in_process_only",
            })
            prompt_context = _bounded_actor_prompt_context(context, compression=compression, max_context_chars=max_context_chars)
            op.close("completed", enabled=True, persisted=False, output_context_chars=prompt_context["context_json_chars"])
            return prompt_context
        except Exception as exc:  # pragma: no cover - depends on optional runtime service
            compression["warning"] = str(exc)
            prompt_context = _bounded_actor_prompt_context(context, compression=compression, max_context_chars=max_context_chars)
            op.close("completed", enabled=False, warning=str(exc), output_context_chars=prompt_context["context_json_chars"])
            return prompt_context


def actor_prompt_spec(actor_id: str) -> dict[str, Any]:
    if actor_id in REVIEW_AGENT_PROMPT_FILES:
        return prompt_spec_from_markdown(REVIEW_AGENT_PROMPT_FILES[actor_id])
    for method_id, scorer_id in SCORER_STAGE_BY_METHOD.items():
        if actor_id == scorer_id:
            return prompt_spec_from_markdown("method-scorer-review.md", method_id=method_id)
    if actor_id in RESEARCH_AGENT_PROMPT_FILES:
        return prompt_spec_from_markdown("research-agent-review.md", actor_id=actor_id)
    return prompt_spec_from_markdown("generic-actor-review.md", actor_id=actor_id)


def build_actor_review_prompt(
    *,
    actor_id: str,
    actor_spec: dict[str, Any],
    context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    prompt_spec = actor_prompt_spec(actor_id)
    available_rag_refs = (context.get("rag_context") or {}).get("citations") if isinstance(context.get("rag_context"), dict) else []
    system_prompt = load_prompt(
        "actor-review-system.md",
        actor_id=actor_id,
        mission=prompt_spec["mission"],
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
    return shared_default_actor_rag_refs({"rag_context": rag_context, "citations": citation_ref_values(rag_context)})


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
    force_reprocess = any(bool((item.get("cache_policy") or {}).get("force_reprocess")) for item in queue)
    lines = [
        "# VC Assistant Run Summary",
        "",
        "Report-only run. The user decides what to review next.",
        "",
        f"Companies in index: {len(analyses)}",
        f"Companies processed this cycle: {processed_count}",
        f"Unchanged companies skipped: {skipped_count}",
        f"Force reprocess: {force_reprocess}",
        "",
        "## Cache Policy",
    ]
    for item in queue:
        policy = item.get("cache_policy") if isinstance(item.get("cache_policy"), dict) else {}
        lines.append(
            f"- {item['company_name']}: {policy.get('freshness') or item['status']} "
            f"({policy.get('decision') or item['status']}; previous_run_id: {policy.get('previous_run_id') or 'none'})"
        )
    lines += [
        "",
        "## Company Scores",
    ]
    for analysis in analyses:
        lines.append(
            f"- {analysis['company_name']}: investment score {analysis.get('investment_score')} "
            f"(evidence quality {analysis.get('evidence_quality_score')}, {str(analysis.get('confidence_band') or 'not_reliable').replace('_', ' ')})"
        )
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
    queue_by_slug = {item["company_slug"]: item for item in queue}
    for analysis in analyses:
        slug = analysis["company_slug"]
        company_dir = output_folder / slug
        evidence = company_records[analysis["company_name"]]
        research_ledger = research_ledgers[analysis["company_name"]]
        sources = flattened_sources(research_ledger)
        warnings = warnings_for_company(analysis, sources)
        analysis["local_evidence_summary"] = summarize_local_evidence(evidence)
        analysis["research_source_summary"] = summarize_research_sources(sources)
        analysis["evidence_artifacts"] = {
            "local_evidence_path": str(company_dir / "evidence.json"),
            "research_sources_path": str(company_dir / "research_sources.json"),
            "research_ledger_path": str(output_folder / "research_ledgers" / f"{slug}.json"),
            "source_records_path": str(company_dir / "source_records.json"),
            "evidence_items_path": str(company_dir / "evidence_items.json"),
            "claim_records_path": str(company_dir / "claims.json"),
            "evidence_graph_path": str(company_dir / "evidence_graph.json"),
            "bayesian_claim_explanations_path": str(company_dir / "bayesian_claim_explanations.json"),
        }
        analysis["evidence"] = compact_local_evidence_for_transport(evidence)
        analysis["research_sources"] = compact_research_sources_for_transport(sources)
        analysis["warnings"] = warnings
        write_json(company_dir / "analysis.json", analysis)
        write_json(company_dir / "method_scores.json", analysis["methods"])
        write_json(company_dir / "research_plan.json", analysis.get("research_plan") or {})
        write_json(company_dir / "agent_tool_trace.json", analysis.get("agent_tool_trace") or [])
        write_json(company_dir / "research_sources.json", sources)
        write_json(company_dir / "sources.json", sources)
        write_json(company_dir / "evidence.json", evidence)
        write_json(company_dir / "source_records.json", analysis.get("source_records") or [])
        write_json(company_dir / "evidence_items.json", analysis.get("evidence_items") or [])
        write_json(company_dir / "claims.json", analysis.get("claim_records") or [])
        write_json(company_dir / "evidence_graph.json", analysis.get("evidence_graph") or {})
        write_json(company_dir / "bayesian_claim_explanations.json", analysis.get("bayesian_claim_explanations") or [])
        write_json(company_dir / "warnings.json", warnings)
        markdown = render_markdown(analysis, sources, evidence)
        (company_dir / "analysis.md").write_text(markdown, encoding="utf-8")
        for name in ("analysis.json", "analysis.md", "method_scores.json", "research_plan.json", "agent_tool_trace.json", "research_sources.json", "sources.json", "evidence.json", "source_records.json", "evidence_items.json", "claims.json", "evidence_graph.json", "bayesian_claim_explanations.json", "warnings.json"):
            output_files.append({"kind": name.rsplit(".", 1)[0], "path": str(company_dir / name), "company": analysis["company_name"]})
        write_json(output_folder / "company_fact_tables" / f"{slug}.json", analysis["fact_table"])
        write_json(output_folder / "research_ledgers" / f"{slug}.json", research_ledger)
        write_json(output_folder / "method_scores" / f"{slug}.json", analysis["methods"])
        write_json(output_folder / "audit_findings" / f"{slug}.json", analysis["audit"])
        write_json(output_folder / "evidence_items" / f"{slug}.json", analysis.get("evidence_items") or [])
        write_json(output_folder / "claim_records" / f"{slug}.json", analysis.get("claim_records") or [])
    index = {
        "blueprint_id": BLUEPRINT_ID,
        "generated_at": utc_now_iso(),
        "report_only": True,
        "cache_policy": build_cache_policy_summary(
            queue,
            processed_company_names=[item["company_name"] for item in queue if item["status"] != "unchanged_skipped"],
            skipped_company_names=[item["company_name"] for item in queue if item["status"] == "unchanged_skipped"],
        ),
        "companies": [
            {
                "company_name": analysis["company_name"],
                "company_slug": analysis["company_slug"],
                "composite_score": analysis["composite_score"],
                "investment_score": analysis.get("investment_score"),
                "evidence_quality_score": analysis.get("evidence_quality_score"),
                "confidence_band": analysis.get("confidence_band"),
                "recommendation": analysis.get("recommendation"),
                "missing_methods": analysis["evidence_summary"]["missing_methods"],
                "processing_status": analysis.get("processing_status"),
                "cached_from_previous_run": bool(analysis.get("cached_from_previous_run")),
                "cache_policy": analysis.get("cache_policy") or (queue_by_slug.get(analysis["company_slug"]) or {}).get("cache_policy"),
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
        policy = item.get("cache_policy") if isinstance(item.get("cache_policy"), dict) else {}
        index_lines.append(
            f"- {item['company_name']}: investment score {item.get('investment_score')} "
            f"(evidence quality {item.get('evidence_quality_score')}, {str(item.get('confidence_band') or 'not_reliable').replace('_', ' ')}) "
            f"({policy.get('freshness') or item.get('processing_status')})"
        )
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


def scoring_fund_profile(config: dict[str, Any]) -> str:
    scoring = config.get("scoring") if isinstance(config.get("scoring"), dict) else {}
    raw = str(scoring.get("fund_profile") or config.get("fund_profile") or "generalist").strip().lower().replace("-", "_")
    return raw if raw in FUND_PROFILE_WEIGHTS else "generalist"


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
            cached_analysis["cache_policy"] = {
                **(queue_item.get("cache_policy") or {}),
                "cache_source": "watch_state_and_company_artifacts",
                "freshness": "unchanged_cached",
                "decision": "reuse_cached_outputs",
            }
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
    append_financial_tool_research(company, records, research_ledger, action_budget=action_budget, run_dir=run_dir)
    reconciliation = reconcile_research(records, research_ledger)
    analysis = build_company_analysis(
        company,
        records,
        research_ledger,
        scoring_workers=scoring_worker_count(resolved_config),
        fund_profile=scoring_fund_profile(resolved_config),
    )
    analysis["processing_status"] = "new_or_changed"
    analysis["cached_from_previous_run"] = False
    analysis["cache_policy"] = {
        **(queue_item.get("cache_policy") or {}),
        "cache_source": "",
        "decision": "process_company_packet",
    }
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


WORKFLOW_STATE_DIRNAME = "workflow_state"
SCORER_METHOD_BY_STAGE = {stage_id: method_id for method_id, stage_id in SCORER_STAGE_BY_METHOD.items()}
METHOD_SCORER_FUNCTIONS = {
    "berkus_method": score_berkus,
    "scorecard_bill_payne_method": score_scorecard,
    "risk_factor_summation_method": score_risk_factor_summation,
    "venture_capital_method": score_venture_capital_method,
    "first_chicago_method": score_first_chicago,
    "comparables_market_multiple_method": score_comparables,
    "cost_to_duplicate_method": score_cost_to_duplicate,
}


def workflow_state_dir(run_dir: Path) -> Path:
    return run_dir / WORKFLOW_STATE_DIRNAME


def workflow_state_file(run_dir: Path, name: str) -> Path:
    return workflow_state_dir(run_dir) / name


def workflow_state_subdir(run_dir: Path, name: str) -> Path:
    return workflow_state_dir(run_dir) / name


def read_workflow_state(run_dir: Path, name: str, default: Any = None) -> Any:
    return read_json_value(workflow_state_file(run_dir, name), default)


def write_workflow_state(run_dir: Path, name: str, value: Any) -> None:
    write_json(workflow_state_file(run_dir, name), value)


def company_state_path(run_dir: Path, folder: str, company_or_slug: str) -> Path:
    return workflow_state_subdir(run_dir, folder) / f"{slugify(company_or_slug)}.json"


def normalized_research_ledger(value: Any) -> dict[str, list[dict[str, Any]]]:
    ledger = value if isinstance(value, dict) else {}
    return {
        stage: list(ledger.get(stage) or []) if isinstance(ledger.get(stage), list) else []
        for stage in RESEARCH_STAGE_IDS
    }


def read_company_research_ledger(run_dir: Path, company: str) -> dict[str, list[dict[str, Any]]]:
    return normalized_research_ledger(read_json_value(company_state_path(run_dir, "research_ledgers", company), {}))


def write_company_research_ledger(run_dir: Path, company: str, ledger: dict[str, list[dict[str, Any]]]) -> None:
    write_json(company_state_path(run_dir, "research_ledgers", company), normalized_research_ledger(ledger))


def read_company_records_state(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    value = read_workflow_state(run_dir, "company_records.json", {})
    if not isinstance(value, dict):
        return {}
    return {
        str(company): list(records) if isinstance(records, list) else []
        for company, records in value.items()
    }


def read_company_work_queue_state(run_dir: Path) -> list[dict[str, Any]]:
    value = read_workflow_state(run_dir, "company_work_queue.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def write_company_analysis_state(run_dir: Path, analysis: dict[str, Any]) -> None:
    write_json(company_state_path(run_dir, "analyses", str(analysis["company_slug"])), analysis)


def read_company_analysis_state(run_dir: Path, company_or_slug: str) -> dict[str, Any]:
    return read_json(company_state_path(run_dir, "analyses", company_or_slug))


def read_all_company_analyses(run_dir: Path) -> list[dict[str, Any]]:
    analyses_dir = workflow_state_subdir(run_dir, "analyses")
    if not analyses_dir.exists():
        return []
    analyses = [
        value
        for path in sorted(analyses_dir.glob("*.json"))
        for value in [read_json(path)]
        if value
    ]
    return sorted(analyses, key=lambda item: item.get("company_slug") or slugify(item.get("company_name", "")))


def read_all_research_ledgers(run_dir: Path, company_names: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {company: read_company_research_ledger(run_dir, company) for company in company_names}


def write_company_method_scores_state(run_dir: Path, company: str, methods: dict[str, dict[str, Any]]) -> None:
    write_json(company_state_path(run_dir, "method_scores", company), methods)


def read_company_method_scores_state(run_dir: Path, company: str) -> dict[str, dict[str, Any]]:
    value = read_json(company_state_path(run_dir, "method_scores", company))
    return {method_id: value[method_id] for method_id in METHOD_IDS if isinstance(value.get(method_id), dict)}


def write_company_reconciliation_state(run_dir: Path, company: str, reconciliation: dict[str, Any]) -> None:
    write_json(company_state_path(run_dir, "reconciliations", company), reconciliation)


def read_company_reconciliation_state(run_dir: Path, company: str) -> dict[str, Any]:
    return read_json(company_state_path(run_dir, "reconciliations", company))


def write_company_research_plan_state(run_dir: Path, company: str, plan: dict[str, Any]) -> None:
    write_json(company_state_path(run_dir, "research_plans", company), plan)


def read_company_research_plan_state(run_dir: Path, company: str) -> dict[str, Any]:
    return read_json(company_state_path(run_dir, "research_plans", company))


def write_company_agent_trace_state(run_dir: Path, company: str, trace: list[dict[str, Any]]) -> None:
    write_json(company_state_path(run_dir, "agent_tool_traces", company), trace)


def read_company_agent_trace_state(run_dir: Path, company: str) -> list[dict[str, Any]]:
    value = read_json_value(company_state_path(run_dir, "agent_tool_traces", company), [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    blueprint_dir = resolve_blueprint_dir()
    resolved_config = load_resolved_config(blueprint_dir / "config" / "default.json", config)
    payload = dict((resolved_config.get("inputs") or {}).get("payload") or {})
    if inputs:
        payload.update(inputs)
    runtime_run_id = run_id or payload.get("run_id") or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    output_folder = resolve_output_folder(payload, resolved_config, inputs)
    payload["output_folder"] = str(output_folder)
    run_dir = resolve_run_dir(output_folder, runtime_run_id, runs_root)
    persisted = read_json(workflow_state_file(run_dir, "runtime_context.json"))
    if persisted:
        output_folder = expand_runtime_path(persisted.get("output_folder") or output_folder)
        run_dir = expand_runtime_path(persisted.get("run_dir") or run_dir)
        document_folder = expand_runtime_path(persisted.get("document_folder") or payload.get("document_folder") or "")
        started_at = str(persisted.get("started_at") or utc_now_iso())
        force_reprocess = bool(persisted.get("force_reprocess"))
        max_cycles = int(persisted.get("max_cycles") or 1)
        payload.update(persisted.get("payload") if isinstance(persisted.get("payload"), dict) else {})
    else:
        document_folder = (
            resolve_existing_path(payload["document_folder"], [blueprint_dir / "payloads", blueprint_dir, blueprint_dir.parent])
            if payload.get("document_folder")
            else blueprint_dir / "payloads" / "examples" / "sample_inputs"
        )
        monitoring = dict(payload.get("monitoring") or {})
        max_cycles = int(monitoring.get("max_cycles") or 1)
        force_reprocess = force_reprocess_enabled(payload, resolved_config)
        started_at = utc_now_iso()
    return {
        "blueprint_dir": blueprint_dir,
        "config": resolved_config,
        "payload": payload,
        "run_id": str(runtime_run_id),
        "output_folder": Path(output_folder),
        "run_dir": Path(run_dir),
        "document_folder": Path(document_folder),
        "max_cycles": max_cycles,
        "force_reprocess": force_reprocess,
        "started_at": started_at,
    }


def persist_runtime_context(ctx: dict[str, Any]) -> None:
    write_workflow_state(
        ctx["run_dir"],
        "runtime_context.json",
        {
            "blueprint_id": BLUEPRINT_ID,
            "run_id": ctx["run_id"],
            "started_at": ctx["started_at"],
            "output_folder": str(ctx["output_folder"]),
            "run_dir": str(ctx["run_dir"]),
            "document_folder": str(ctx["document_folder"]),
            "max_cycles": ctx["max_cycles"],
            "force_reprocess": bool(ctx["force_reprocess"]),
            "payload": ctx["payload"],
        },
    )


def elapsed_ms_from_started_at(started_at: str) -> float:
    try:
        parsed = datetime.fromisoformat(started_at)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() * 1000)
    except Exception:
        return 0.0


def write_failed_run(ctx: dict[str, Any], error: Exception | str) -> None:
    write_json(
        ctx["run_dir"] / "run.json",
        {
            "run_id": ctx["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "failed",
            "error": str(error),
            "finished_at": utc_now_iso(),
        },
    )


def step_result(ctx: dict[str, Any], step_id: str, **metadata: Any) -> dict[str, Any]:
    result = {
        "run_id": ctx["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "workflow_step_id": step_id,
        "runtime_step_mode": "workflow_step_handler",
        **metadata,
    }
    write_json(ctx["run_dir"] / f"{step_id}_result.json", result)
    write_json(workflow_state_file(ctx["run_dir"], f"{step_id}_result.json"), result)
    return result


def complete_runtime_step(ctx: dict[str, Any], step_id: str, payload: dict[str, Any]) -> None:
    append_event(ctx["run_dir"], f"{step_id}_completed", {"step_id": step_id, "runtime_step_mode": "workflow_step_handler", **payload})


def load_action_budget_state(ctx: dict[str, Any]) -> ActionBudget:
    budget = build_action_budget(ctx["config"])
    state = read_workflow_state(ctx["run_dir"], "action_ledger.json", {})
    if isinstance(state, dict) and "budget" in state:
        budget.budget = int(state.get("budget") or budget.budget)
        budget.used = int(state.get("used") or 0)
        actions = state.get("actions")
        budget.actions = [dict(item) for item in actions if isinstance(item, dict)] if isinstance(actions, list) else []
    return budget


def persist_action_budget_state(ctx: dict[str, Any], action_budget: ActionBudget) -> dict[str, Any]:
    summary = action_budget.summary(include_actions=True)
    write_workflow_state(ctx["run_dir"], "action_ledger.json", summary)
    return summary


def init_runtime_llm(ctx: dict[str, Any], action_budget: ActionBudget, llm_client: Any | None = None) -> tuple[Any, LlmCallLimiter]:
    limiter = build_llm_call_limiter(ctx["config"])
    require_live = llm_requires_live(ctx["config"])
    try:
        with observed_operation(ctx["run_dir"], phase="llm_init", operation="actor_llm.init"):
            llm = BudgetedLLM(
                _get_configured_actor_llm(ctx["config"], llm_client),
                action_budget,
                require_live=require_live,
                limiter=limiter,
                run_dir=ctx["run_dir"],
            )
            return llm, limiter
    except Exception as exc:
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "actor_llm.init", "status": "required_actor_llm_init_failed", "error": str(exc)})
        write_failed_run(ctx, exc)
        raise


def prepare_runtime_knowledge_rag(ctx: dict[str, Any], *, stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    active_knowledge = load_vc_knowledge(ctx["blueprint_dir"])
    with observed_operation(
        ctx["run_dir"],
        phase="knowledge_rag",
        operation="prepare",
        embedding_provider=((ctx["config"].get("knowledge_rag") or {}).get("embedding_provider") if isinstance(ctx["config"].get("knowledge_rag"), dict) else ""),
        embedding_model=((ctx["config"].get("knowledge_rag") or {}).get("embedding_model") if isinstance(ctx["config"].get("knowledge_rag"), dict) else ""),
    ) as op:
        knowledge_rag = prepare_knowledge_rag(
            blueprint_dir=ctx["blueprint_dir"],
            resolved_config=ctx["config"],
            active_knowledge=active_knowledge,
            run_dir=ctx["run_dir"],
        )
        op.close(
            "completed",
            rag_status=knowledge_rag.get("status"),
            indexed_count=(knowledge_rag.get("index_summary") or {}).get("indexed_count") if isinstance(knowledge_rag.get("index_summary"), dict) else None,
        )
    try:
        require_ready_rag(knowledge_rag, stage=stage, run_dir=ctx["run_dir"])
    except Exception as exc:
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "knowledge_rag.index", "status": "required_rag_failed", "error": str(exc)})
        write_failed_run(ctx, exc)
        raise
    return active_knowledge, knowledge_rag


def build_runtime_services(
    ctx: dict[str, Any],
    *,
    llm_client: Any | None = None,
    need_llm: bool = False,
    rag_stage: str = "",
) -> dict[str, Any]:
    action_budget = load_action_budget_state(ctx)
    active_knowledge: dict[str, Any] = {}
    knowledge_rag: dict[str, Any] = {}
    if rag_stage:
        active_knowledge, knowledge_rag = prepare_runtime_knowledge_rag(ctx, stage=rag_stage)
    llm = None
    limiter = build_llm_call_limiter(ctx["config"])
    if need_llm:
        llm, limiter = init_runtime_llm(ctx, action_budget, llm_client)
    return {
        "action_budget": action_budget,
        "active_knowledge": active_knowledge,
        "knowledge_rag": knowledge_rag,
        "llm": llm,
        "llm_limiter": limiter,
    }


def step_actor_review_selected(ctx: dict[str, Any], step_id: str) -> bool:
    return step_id in set(actor_review_config(ctx["config"]).get("llm_actor_ids") or [])


def workflow_state_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    queue = read_company_work_queue_state(ctx["run_dir"])
    analyses = read_all_company_analyses(ctx["run_dir"])
    return {
        "document_file_count": len(read_workflow_state(ctx["run_dir"], "document_files.json", []) or []),
        "company_record_count": len(company_records),
        "queued_company_count": len(queue),
        "analysis_count": len(analyses),
        "queued_statuses": sorted({str(item.get("status") or "") for item in queue}),
        "companies": sorted(company_records),
    }


def load_actor_findings_state(ctx: dict[str, Any]) -> dict[str, Any]:
    return read_workflow_state(ctx["run_dir"], "actor_findings.json", {}) or {}


def write_actor_findings_state(ctx: dict[str, Any], actor_findings: dict[str, Any]) -> None:
    write_workflow_state(ctx["run_dir"], "actor_findings.json", actor_findings)


def load_actor_review_warnings_state(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    value = read_workflow_state(ctx["run_dir"], "actor_review_warnings.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def write_actor_review_warnings_state(ctx: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    write_workflow_state(ctx["run_dir"], "actor_review_warnings.json", warnings)


def run_step_actor_review(
    ctx: dict[str, Any],
    step_id: str,
    services: dict[str, Any],
    *,
    llm_client: Any | None = None,
) -> None:
    if not step_actor_review_selected(ctx, step_id):
        return
    action_budget = services.get("action_budget") or load_action_budget_state(ctx)
    active_knowledge = services.get("active_knowledge") or {}
    knowledge_rag = services.get("knowledge_rag") or {}
    if not knowledge_rag:
        active_knowledge, knowledge_rag = prepare_runtime_knowledge_rag(ctx, stage=step_id)
    llm = services.get("llm")
    if llm is None:
        llm, limiter = init_runtime_llm(ctx, action_budget, llm_client)
        services["llm"] = llm
        services["llm_limiter"] = limiter
    actor_findings = load_actor_findings_state(ctx)
    actor_review_warnings = load_actor_review_warnings_state(ctx)
    actor_rag_context = retrieve_knowledge_rag_context(
        knowledge_rag=knowledge_rag,
        query=f"{step_id} VC workflow quality evidence grounding scoring research report-only boundary",
        stage=step_id,
        run_dir=ctx["run_dir"],
    )
    require_ready_rag(knowledge_rag, stage=step_id, context=actor_rag_context, min_citations=1, run_dir=ctx["run_dir"])
    prompt_rag_context = {
        key: value
        for key, value in dict(actor_rag_context).items()
        if key not in {"context", "chunks"}
    }
    prompt_rag_context["citation_count"] = len(prompt_rag_context.get("citations") or [])
    active_knowledge_prompt_ref = active_knowledge_reference(active_knowledge)
    active_knowledge_prompt_ref.pop("title", None)
    review_context = {
        "blueprint_id": BLUEPRINT_ID,
        "workflow_step_id": step_id,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
        "state_summary": workflow_state_summary(ctx),
        "active_knowledge": active_knowledge_prompt_ref,
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "rag_context": prompt_rag_context,
        "privacy_controls": {
            "public_research_queries": "company names, domains, categories, and non-confidential public claims only",
            "local_document_text": "not included in actor-review context",
        },
        "memory_boundary": {
            "rag_knowledge": "persistent Redis-backed knowledge index",
            "working_memory": "transient local prompt context; not written to Redis",
        },
    }
    try:
        actor_findings = run_vc_actor_reviews(
            config=ctx["config"],
            llm=llm,
            actor_ids=[step_id],
            state={"actor_findings": actor_findings},
            context=review_context,
            knowledge_rag=knowledge_rag,
            event_sink=ctx["run_dir"],
        )
    except Exception as exc:
        if llm_requires_live(ctx["config"]) or knowledge_rag_is_required(knowledge_rag):
            append_event(ctx["run_dir"], "tool_call_failed", {"tool": "actor_llm", "status": "required_actor_review_failed", "agent_id": step_id, "error": str(exc)})
            write_failed_run(ctx, exc)
            raise
        fallback = actor_review_unavailable_findings([step_id], exc)
        actor_findings.update(fallback)
        actor_review_warnings.append(
            {
                "kind": "actor_review",
                "status": "actor_review_unavailable",
                "message": "One or more LLM actor reviews failed after deterministic reports were generated; report artifacts were preserved.",
                "error": str(exc),
                "affected_actor_count": 1,
            }
        )
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "actor_llm", "status": "actor_review_unavailable", "agent_id": step_id, "error": str(exc)})
    write_actor_findings_state(ctx, actor_findings)
    write_actor_review_warnings_state(ctx, actor_review_warnings)
    persist_action_budget_state(ctx, action_budget)


def ensure_all_actor_findings(ctx: dict[str, Any]) -> dict[str, Any]:
    actor_specs = resolve_actor_specs(ctx["config"])
    actor_findings = load_actor_findings_state(ctx)
    for actor_id in WORKFLOW_STEP_IDS:
        if actor_id not in actor_findings:
            actor_findings[actor_id] = not_llm_reviewed_actor_finding(actor_id, dict(actor_specs.get(actor_id) or {}))
    write_actor_findings_state(ctx, actor_findings)
    return actor_findings


def normalized_actor_review_warnings(ctx: dict[str, Any], actor_findings: dict[str, Any]) -> list[dict[str, Any]]:
    unavailable = [
        str(finding.get("error") or "")
        for finding in actor_findings.values()
        if isinstance(finding, dict) and finding.get("provider") == "actor_review_unavailable"
    ]
    if unavailable:
        return [
            {
                "kind": "actor_review",
                "status": "actor_review_unavailable",
                "message": "One or more LLM actor reviews failed after deterministic reports were generated; report artifacts were preserved.",
                "error": unavailable[0],
                "affected_actor_count": len(unavailable),
            }
        ]
    shared_warnings = shared_normalize_actor_review_warnings(actor_findings)
    return shared_warnings or load_actor_review_warnings_state(ctx)


def group_document_file_records(document_folder: Path, files: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        path = Path(str(item.get("path") or ""))
        try:
            relative = path.relative_to(document_folder)
        except ValueError:
            relative = path
        if len(relative.parts) > 1:
            company = relative.parts[0].replace("_", " ").replace("-", " ").title()
        else:
            company = path.stem.replace("_", " ").replace("-", " ").title()
        grouped.setdefault(company, []).append(item)
    return dict(sorted(grouped.items(), key=lambda entry: slugify(entry[0])))


def build_company_analysis_from_method_scores(
    company: str,
    records: list[dict[str, Any]],
    research_ledger: dict[str, list[dict[str, Any]]],
    methods: dict[str, dict[str, Any]],
    fund_profile: str | None = None,
) -> dict[str, Any]:
    sources = [source for stage_sources in research_ledger.values() for source in stage_sources]
    facts = build_fact_table(company, records, sources)
    ordered_methods = {method_id: methods[method_id] for method_id in METHOD_IDS}
    audit = audit_method_scores(ordered_methods, facts)
    scored = [item["score"] for item in ordered_methods.values() if isinstance(item.get("score"), (int, float))]
    missing_methods = [method_id for method_id, method in ordered_methods.items() if method["status"] == "insufficient_evidence"]
    substantive_sources = [source for source in sources if is_substantive_public_source(source)]
    evidence_layer = build_company_evidence_layer(company, records, sources, fund_profile=fund_profile)
    evidence_summary_layer = evidence_layer["company_evidence_summary"]
    composite_score = evidence_summary_layer["investment_score"]
    method_average_score = round(sum(scored) / len(scored), 2) if scored else None
    return {
        "company_name": company,
        "company_slug": slugify(company),
        "composite_score": composite_score,
        "investment_score": composite_score,
        "method_average_score": method_average_score,
        "evidence_quality_score": evidence_summary_layer["evidence_quality_score"],
        "confidence_band": evidence_summary_layer["confidence_band"],
        "recommendation": evidence_summary_layer["recommendation"],
        "dimension_scores": evidence_summary_layer["dimension_scores"],
        "score_caps": evidence_summary_layer["score_caps"],
        "fund_profile": evidence_layer["fund_profile"],
        "method_count": len(ordered_methods),
        "methods": ordered_methods,
        "method_score_appendix": ordered_methods,
        "source_records": evidence_layer["source_records"],
        "evidence_items": evidence_layer["evidence_items"],
        "claim_records": evidence_layer["claim_records"],
        "evidence_graph": evidence_layer["evidence_graph"],
        "company_evidence_summary": evidence_summary_layer,
        "truth_discovery": evidence_layer.get("truth_discovery", {}),
        "bayesian_claim_explanations": evidence_layer.get("bayesian_claim_explanations", []),
        "fact_table": facts,
        "audit": audit,
        "evidence_summary": {
            "document_count": len(records),
            "source_count": len(sources),
            "substantive_source_count": len(substantive_sources),
            "financial_tool_source_count": len([source for source in sources if source.get("skill") == "financial_public_data_tool"]),
            "missing_methods": missing_methods,
            "composite_score_evidence": {
                "status": "scored" if composite_score is not None else "insufficient_evidence",
                "scored_method_count": len(scored),
                "method_ids": [method_id for method_id, method in ordered_methods.items() if isinstance(method.get("score"), (int, float))],
                "reason": "Composite is the confidence-weighted investment score from normalized claims; method scores are retained as an appendix." if composite_score is not None else "No normalized claim evidence was available for a numeric score.",
                "method_average_score": method_average_score,
                "evidence_quality_score": evidence_summary_layer["evidence_quality_score"],
                "confidence_band": evidence_summary_layer["confidence_band"],
                "fund_profile": evidence_layer["fund_profile"],
                "truth_discovery_eligible_claim_count": len((evidence_layer.get("truth_discovery") or {}).get("eligible_claim_ids") or []),
                "bayesian_claim_explanation_count": len(evidence_layer.get("bayesian_claim_explanations") or []),
            },
        },
        "result_evidence": {
            "composite_score": {
                "value": composite_score,
                "why": "Confidence-weighted normalized claims by fund profile, with hard caps for missing team, traction, product, or evidence quality." if composite_score is not None else "No scored normalized claims were available.",
                "evidence_refs": sorted({ev.get("evidence_id") for ev in evidence_layer["evidence_items"] if ev.get("evidence_id")})[:20],
                "missing_evidence": dedupe_list(
                    [
                        missing
                        for claim in evidence_layer["claim_records"]
                        for missing in (claim.get("required_next_evidence") or [])[:2]
                        if int(claim.get("net_confidence") or 0) < 70
                    ],
                    20,
                ),
                "score_caps": evidence_summary_layer["score_caps"],
            },
            "research": {
                "source_count": len(sources),
                "substantive_source_count": len(substantive_sources),
                "budget_or_source_warnings": [source.get("warning") for source in sources if source.get("warning")],
            },
        },
        "decision_policy": "report_only_user_decides",
    }


def hydrate_cached_company_state(
    ctx: dict[str, Any],
    company_records: dict[str, list[dict[str, Any]]],
    company_work_queue: list[dict[str, Any]],
    knowledge_rag: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    for item in company_work_queue:
        if item.get("status") != "unchanged_skipped":
            continue
        company = str(item["company_name"])
        cached_analysis = load_cached_company_analysis(ctx["output_folder"], company)
        cached_ledger = load_cached_research_ledger(ctx["output_folder"], company)
        if not cached_analysis or cached_ledger is None:
            item["status"] = "new_or_changed"
            item["cache_status"] = "missing_cached_report_reprocessed"
            item.setdefault("cache_policy", {})["freshness"] = "fresh_or_changed"
            item.setdefault("cache_policy", {})["decision"] = "process_company_packet"
            item.setdefault("cache_policy", {})["cache_source"] = ""
            continue
        records = company_records.get(company, [])
        reconciliation = cached_analysis.get("research_reconciliation") or reconcile_research(records, cached_ledger)
        cached_analysis["processing_status"] = "unchanged_skipped"
        cached_analysis["cached_from_previous_run"] = True
        cached_analysis["research_reconciliation"] = reconciliation
        cached_analysis["cache_policy"] = {
            **(item.get("cache_policy") or {}),
            "cache_source": "watch_state_and_company_artifacts",
            "freshness": "unchanged_cached",
            "decision": "reuse_cached_outputs",
        }
        if "research_plan" not in cached_analysis:
            internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
            cached_analysis["research_plan"] = build_adaptive_research_plan(company, records, internet)
        cached_analysis.setdefault("agent_tool_trace", [])
        cached_analysis.setdefault("research_plan", {}).setdefault("knowledge_rag", public_knowledge_rag_state(knowledge_rag))
        write_company_analysis_state(ctx["run_dir"], cached_analysis)
        write_company_research_ledger(ctx["run_dir"], company, cached_ledger)
        write_company_reconciliation_state(ctx["run_dir"], company, reconciliation)
        write_company_method_scores_state(ctx["run_dir"], company, cached_analysis.get("methods") or {})
        write_company_research_plan_state(ctx["run_dir"], company, cached_analysis.get("research_plan") or {})
        write_company_agent_trace_state(ctx["run_dir"], company, cached_analysis.get("agent_tool_trace") or [])
    return company_work_queue


def processed_and_skipped_company_names(company_work_queue: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    processed = [str(item["company_name"]) for item in company_work_queue if item.get("status") != "unchanged_skipped"]
    skipped = [str(item["company_name"]) for item in company_work_queue if item.get("status") == "unchanged_skipped"]
    return processed, skipped


def run_startup_folder_watcher_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    ctx["run_dir"].mkdir(parents=True, exist_ok=True)
    ctx["output_folder"].mkdir(parents=True, exist_ok=True)
    persist_runtime_context(ctx)
    write_json(ctx["run_dir"] / "config.json", ctx["config"])
    write_json(
        ctx["run_dir"] / "inputs.json",
        {"payload": ctx["payload"], "document_folder": str(ctx["document_folder"]), "force_reprocess": ctx["force_reprocess"]},
    )
    write_json(ctx["run_dir"] / "run.json", {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": ctx["started_at"]})
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "watch_cycle_started", {"cycle": 1, "max_cycles": ctx["max_cycles"]})
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})
    with observed_operation(ctx["run_dir"], phase="startup_folder_watcher", operation="discover_document_files", path_hash=stable_text_hash(ctx["document_folder"]), supported_suffixes=sorted(SUPPORTED_SUFFIXES)) as op:
        files = [
            {
                "path": str(path),
                "relative_path": str(path.relative_to(ctx["document_folder"])) if path.is_relative_to(ctx["document_folder"]) else path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }
            for path in _document_paths(ctx["document_folder"])
        ]
        write_workflow_state(ctx["run_dir"], "document_files.json", files)
        op.close("completed", document_file_count=len(files))
    complete_runtime_step(ctx, "startup_folder_watcher", {"document_file_count": len(files), "document_folder": str(ctx["document_folder"])})
    return step_result(ctx, "startup_folder_watcher", document_file_count=len(files))


def run_company_packet_grouper_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    files = read_workflow_state(ctx["run_dir"], "document_files.json", [])
    files = [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []
    groups = group_document_file_records(ctx["document_folder"], files)
    packets = [
        {
            "company_name": company,
            "company_slug": slugify(company),
            "document_count": len(items),
            "source_refs": [item.get("path") for item in items],
        }
        for company, items in groups.items()
    ]
    write_workflow_state(ctx["run_dir"], "company_packet_groups.json", packets)
    complete_runtime_step(ctx, "company_packet_grouper", {"company_count": len(packets), "document_file_count": len(files)})
    return step_result(ctx, "company_packet_grouper", company_count=len(packets))


def run_document_evidence_extractor_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    try:
        with observed_operation(ctx["run_dir"], phase="document_evidence_extractor", operation="scan_documents", path_hash=stable_text_hash(ctx["document_folder"]), supported_suffixes=sorted(SUPPORTED_SUFFIXES)) as op:
            company_records = scan_documents(ctx["document_folder"], ctx["config"])
            if not company_records:
                company_records = {"Sample Startup": []}
            op.close("completed", company_count=len(company_records), document_count=sum(len(records) for records in company_records.values()))
    except OcrRequiredError as exc:
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "llm_ocr.extract_document_folder", "status": "required_ocr_failed", "error": str(exc)})
        write_failed_run(ctx, exc)
        raise
    write_workflow_state(ctx["run_dir"], "company_records.json", company_records)
    complete_runtime_step(
        ctx,
        "document_evidence_extractor",
        {"company_count": len(company_records), "document_count": sum(len(records) for records in company_records.values())},
    )
    return step_result(ctx, "document_evidence_extractor", company_count=len(company_records))


def run_claim_normalizer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    previous_state = load_watch_state(ctx["output_folder"])
    company_work_queue = build_company_work_queue(company_records, previous_state, force_reprocess=ctx["force_reprocess"])
    company_work_queue = hydrate_cached_company_state(ctx, company_records, company_work_queue)
    write_json(ctx["output_folder"] / "company_work_queue.json", company_work_queue)
    write_json(ctx["run_dir"] / "company_work_queue.json", company_work_queue)
    write_workflow_state(ctx["run_dir"], "company_work_queue.json", company_work_queue)
    processed, skipped = processed_and_skipped_company_names(company_work_queue)
    complete_runtime_step(ctx, "claim_normalizer", {"company_count": len(processed), "skipped_company_count": len(skipped)})
    return step_result(ctx, "claim_normalizer", processed_company_count=len(processed), skipped_company_count=len(skipped))


def run_research_planner_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
    agentic = agentic_research_config(ctx["config"])
    need_agentic_planner = bool(agentic.get("enabled")) and _agent_stage_enabled(agentic, "research_planner")
    need_llm = need_agentic_planner or step_actor_review_selected(ctx, "research_planner")
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage="research_planner" if need_llm else "")
    knowledge_rag = services.get("knowledge_rag") or {}
    llm = services.get("llm")
    action_budget = services["action_budget"]
    planned_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        plan = build_adaptive_research_plan(company, records, internet)
        write_company_research_plan_state(ctx["run_dir"], company, plan)
        planned_count += 1
        if item.get("status") == "unchanged_skipped":
            analysis = read_company_analysis_state(ctx["run_dir"], company)
            if analysis:
                analysis["research_plan"] = plan
                write_company_analysis_state(ctx["run_dir"], analysis)
            continue
        if need_agentic_planner and llm is not None:
            trace = read_company_agent_trace_state(ctx["run_dir"], company)
            _, planner_sources = run_agentic_research_stage(
                company=company,
                stage="research_planner",
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
                llm=llm,
                agentic=agentic,
                trace=trace,
                knowledge_rag=knowledge_rag,
            )
            ledger = read_company_research_ledger(ctx["run_dir"], company)
            ledger["company_identity_researcher"] = planner_sources + ledger.get("company_identity_researcher", [])
            write_company_research_ledger(ctx["run_dir"], company, ledger)
            write_company_agent_trace_state(ctx["run_dir"], company, trace)
    run_step_actor_review(ctx, "research_planner", services, llm_client=llm_client)
    persist_action_budget_state(ctx, action_budget)
    complete_runtime_step(ctx, "research_planner", {"company_count": planned_count})
    return step_result(ctx, "research_planner", company_count=planned_count)


def run_research_stage_step(ctx: dict[str, Any], step_id: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
    internet_disabled = internet.get("enabled") is False
    agentic = agentic_research_config(ctx["config"])
    need_agentic = bool(agentic.get("enabled")) and _agent_stage_enabled(agentic, step_id)
    need_llm = need_agentic or step_actor_review_selected(ctx, step_id)
    append_debug_record_if_enabled(
        ctx,
        "debug_research_stage_started",
        {
            "step_id": step_id,
            "company_queue_count": len(company_work_queue),
            "company_record_count": len(company_records),
            "internet_disabled": internet_disabled,
            "need_agentic": need_agentic,
            "need_llm": need_llm,
            "agentic_enabled": bool(agentic.get("enabled")),
            "fake_llm": fake_llm_mode_enabled(ctx["config"]),
            "fake_skills": fake_skills_mode_enabled(ctx["config"]),
        },
    )
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage=step_id if need_llm else "")
    llm = services.get("llm")
    knowledge_rag = services.get("knowledge_rag") or {}
    action_budget = services["action_budget"]
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            append_debug_record_if_enabled(
                ctx,
                "debug_research_company_skipped",
                {"step_id": step_id, "company": company, "status": item.get("status")},
            )
            continue
        if internet_disabled:
            ledger = read_company_research_ledger(ctx["run_dir"], company)
            ledger.setdefault(step_id, [])
            write_company_research_ledger(ctx["run_dir"], company, ledger)
            processed_count += 1
            append_debug_record_if_enabled(
                ctx,
                "debug_research_company_completed",
                {
                    "step_id": step_id,
                    "company": company,
                    "internet_disabled": True,
                    "source_count": 0,
                    "ledger_stage_count": len(ledger.get(step_id, [])),
                },
            )
            continue
        records = company_records.get(company, [])
        plan = read_company_research_plan_state(ctx["run_dir"], company) or build_adaptive_research_plan(company, records, internet)
        staged_queries = plan.get("stage_queries") if isinstance(plan.get("stage_queries"), dict) else {}
        query = staged_queries.get(step_id) or plan.get("queries") or [company]
        trace = read_company_agent_trace_state(ctx["run_dir"], company)
        append_debug_record_if_enabled(
            ctx,
            "debug_research_company_started",
            {
                "step_id": step_id,
                "company": company,
                "record_count": len(records),
                "query_count": len(query) if isinstance(query, list) else 1,
                "existing_trace_count": len(trace),
                "agentic": need_agentic and llm is not None,
            },
        )
        if need_agentic and llm is not None:
            stage, sources = run_agentic_research_stage(
                company=company,
                stage=step_id,
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
                llm=llm,
                agentic=agentic,
                trace=trace,
                knowledge_rag=knowledge_rag,
            )
            stage, sources = _with_agentic_gap_fill(
                company=company,
                stage=stage,
                sources=sources,
                query=query,
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
            )
        else:
            stage, sources = _research_one_stage(company, step_id, query, plan, internet, ctx["run_dir"], action_budget)
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        ledger[stage] = ledger.get(stage, []) + sources
        write_company_research_ledger(ctx["run_dir"], company, ledger)
        write_company_agent_trace_state(ctx["run_dir"], company, trace)
        processed_count += 1
        append_debug_record_if_enabled(
            ctx,
            "debug_research_company_completed",
            {
                "step_id": step_id,
                "company": company,
                "stage": stage,
                "source_count": len(sources),
                "ledger_stage_count": len(ledger.get(stage, [])),
                "trace_count": len(trace),
                "action_budget_class": action_budget.__class__.__name__,
            },
        )
    run_step_actor_review(ctx, step_id, services, llm_client=llm_client)
    persist_action_budget_state(ctx, action_budget)
    complete_runtime_step(ctx, step_id, {"company_count": processed_count, "skipped_company_count": skipped_count})
    append_debug_record_if_enabled(
        ctx,
        "debug_research_stage_completed",
        {
            "step_id": step_id,
            "processed_company_count": processed_count,
            "skipped_company_count": skipped_count,
        },
    )
    return step_result(ctx, step_id, processed_company_count=processed_count, skipped_company_count=skipped_count)


def run_research_reconciler_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    need_llm = step_actor_review_selected(ctx, "research_reconciler")
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage="research_reconciler" if need_llm else "")
    action_budget = services["action_budget"]
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            continue
        records = company_records.get(company, [])
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        append_financial_tool_research(company, records, ledger, action_budget=action_budget, run_dir=ctx["run_dir"])
        reconciliation = reconcile_research(records, ledger)
        write_company_research_ledger(ctx["run_dir"], company, ledger)
        write_company_reconciliation_state(ctx["run_dir"], company, reconciliation)
        processed_count += 1
    run_step_actor_review(ctx, "research_reconciler", services, llm_client=llm_client)
    persist_action_budget_state(ctx, action_budget)
    complete_runtime_step(ctx, "research_reconciler", {"company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, "research_reconciler", processed_company_count=processed_count, skipped_company_count=skipped_count)


def run_scorer_step(ctx: dict[str, Any], step_id: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    method_id = SCORER_METHOD_BY_STAGE[step_id]
    scorer = METHOD_SCORER_FUNCTIONS[method_id]
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    need_llm = step_actor_review_selected(ctx, step_id)
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage=step_id if need_llm else "")
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            continue
        records = company_records.get(company, [])
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        facts = build_fact_table(company, records, flattened_sources(ledger))
        methods = read_company_method_scores_state(ctx["run_dir"], company)
        methods[method_id] = scorer(facts)
        write_company_method_scores_state(ctx["run_dir"], company, methods)
        write_json(company_state_path(ctx["run_dir"], "company_fact_tables", company), facts)
        processed_count += 1
    run_step_actor_review(ctx, step_id, services, llm_client=llm_client)
    persist_action_budget_state(ctx, services["action_budget"])
    complete_runtime_step(ctx, step_id, {"method_id": method_id, "company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, step_id, method_id=method_id, processed_company_count=processed_count, skipped_company_count=skipped_count)


def run_score_consistency_auditor_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    need_llm = step_actor_review_selected(ctx, "score_consistency_auditor")
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage="score_consistency_auditor" if need_llm else "")
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            continue
        records = company_records.get(company, [])
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        methods = read_company_method_scores_state(ctx["run_dir"], company)
        missing_methods = [method_id for method_id in METHOD_IDS if method_id not in methods]
        if missing_methods:
            raise RuntimeError(f"Missing method scores for {company}: {', '.join(missing_methods)}")
        analysis = build_company_analysis_from_method_scores(
            company,
            records,
            ledger,
            methods,
            fund_profile=scoring_fund_profile(ctx["config"]),
        )
        analysis["processing_status"] = "new_or_changed"
        analysis["cached_from_previous_run"] = False
        analysis["cache_policy"] = {
            **(item.get("cache_policy") or {}),
            "cache_source": "",
            "decision": "process_company_packet",
        }
        analysis["research_reconciliation"] = read_company_reconciliation_state(ctx["run_dir"], company) or reconcile_research(records, ledger)
        analysis["research_plan"] = read_company_research_plan_state(ctx["run_dir"], company)
        analysis["agent_tool_trace"] = read_company_agent_trace_state(ctx["run_dir"], company)
        analysis.setdefault("research_plan", {})["knowledge_rag"] = public_knowledge_rag_state(services.get("knowledge_rag") or {})
        analysis["research_plan"]["agentic_research"] = {
            "enabled": bool(agentic_research_config(ctx["config"]).get("enabled")),
            "agent_ids": agentic_research_config(ctx["config"]).get("agent_ids"),
            "allowed_tools": agentic_research_config(ctx["config"]).get("allowed_tools"),
            "max_iterations_per_agent": agentic_research_config(ctx["config"]).get("max_iterations_per_agent"),
            "max_tool_calls_per_agent": agentic_research_config(ctx["config"]).get("max_tool_calls_per_agent"),
            "stop_reasons": {trace.get("agent_id"): trace.get("stop_reason") for trace in analysis["agent_tool_trace"]},
        }
        write_company_analysis_state(ctx["run_dir"], analysis)
        write_json(company_state_path(ctx["run_dir"], "audit_findings", company), analysis["audit"])
        processed_count += 1
    run_step_actor_review(ctx, "score_consistency_auditor", services, llm_client=llm_client)
    persist_action_budget_state(ctx, services["action_budget"])
    complete_runtime_step(ctx, "score_consistency_auditor", {"company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, "score_consistency_auditor", processed_company_count=processed_count, skipped_company_count=skipped_count)


def run_company_report_writer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    analyses = read_all_company_analyses(ctx["run_dir"])
    research_ledgers = read_all_research_ledgers(ctx["run_dir"], [analysis["company_name"] for analysis in analyses])
    output_files = write_company_outputs(ctx["output_folder"], analyses, company_records, research_ledgers, company_work_queue)
    watch_state = update_watch_state(ctx["output_folder"], ctx["run_dir"], company_work_queue, run_id=ctx["run_id"])
    for analysis in analyses:
        write_company_analysis_state(ctx["run_dir"], analysis)
    write_workflow_state(ctx["run_dir"], "output_files.json", output_files)
    write_workflow_state(ctx["run_dir"], "watch_state.json", watch_state)
    services = build_runtime_services(
        ctx,
        llm_client=llm_client,
        need_llm=step_actor_review_selected(ctx, "company_report_writer"),
        rag_stage="company_report_writer" if step_actor_review_selected(ctx, "company_report_writer") else "",
    )
    run_step_actor_review(ctx, "company_report_writer", services, llm_client=llm_client)
    persist_action_budget_state(ctx, services["action_budget"])
    complete_runtime_step(ctx, "company_report_writer", {"output_folder": str(ctx["output_folder"]), "output_file_count": len(output_files)})
    append_event(ctx["run_dir"], "watch_cycle_completed", {"cycle": 1, "companies": len(company_records)})
    return step_result(ctx, "company_report_writer", output_file_count=len(output_files))


def run_batch_index_writer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    analyses = read_all_company_analyses(ctx["run_dir"])
    research_ledgers = read_all_research_ledgers(ctx["run_dir"], [analysis["company_name"] for analysis in analyses])
    output_files = read_workflow_state(ctx["run_dir"], "output_files.json", []) or []
    output_files = [item for item in output_files if isinstance(item, dict)]
    services = build_runtime_services(
        ctx,
        llm_client=llm_client,
        need_llm=step_actor_review_selected(ctx, "batch_index_writer"),
        rag_stage="batch_indexing",
    )
    active_knowledge = services.get("active_knowledge") or load_vc_knowledge(ctx["blueprint_dir"])
    knowledge_rag = services.get("knowledge_rag") or {}
    run_step_actor_review(ctx, "batch_index_writer", services, llm_client=llm_client)
    action_ledger = persist_action_budget_state(ctx, services["action_budget"])
    actor_findings = ensure_all_actor_findings(ctx)
    actor_review_warnings = normalized_actor_review_warnings(ctx, actor_findings)
    write_actor_review_warnings_state(ctx, actor_review_warnings)
    processed_company_names, skipped_company_names = processed_and_skipped_company_names(company_work_queue)
    research_coverage = build_research_coverage(research_ledgers)
    method_coverage = build_method_coverage(analyses)
    cache_policy_summary = build_cache_policy_summary(
        company_work_queue,
        processed_company_names=processed_company_names,
        skipped_company_names=skipped_company_names,
    )
    artifact_quality = build_artifact_quality_report(
        analyses=analyses,
        company_records=company_records,
        research_ledgers=research_ledgers,
        output_files=output_files,
        knowledge_rag=knowledge_rag,
        actor_findings=actor_findings,
        actor_review_settings=actor_review_config(ctx["config"]),
    )
    observation_summary = observation_trace_summary(ctx["run_dir"])
    run_health = build_run_health_report(
        run_id=ctx["run_id"],
        started_at=ctx["started_at"],
        elapsed_ms=elapsed_ms_from_started_at(ctx["started_at"]),
        artifact_quality=artifact_quality,
        observation_summary=observation_summary,
        action_ledger=action_ledger,
        knowledge_rag=knowledge_rag,
        research_ledgers=research_ledgers,
        cache_policy_summary=cache_policy_summary,
        actor_review_warnings=actor_review_warnings,
        actor_review_settings=actor_review_config(ctx["config"]),
        llm_limiter=services["llm_limiter"],
    )
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
    company_evidence_summaries = build_company_evidence_summaries(analyses, company_records, research_ledgers)
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
        "source_refs": ["inputs.json", "events.jsonl", "llm_rag_trace.jsonl", "result.json", "final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json", "company_index.json", KNOWLEDGE_PLAYBOOK_RELATIVE_PATH],
        "active_knowledge": active_knowledge_reference(active_knowledge),
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
        "company_evidence_summaries": company_evidence_summaries,
        "research_warnings": [*budget_warnings, *knowledge_rag_warnings],
        "actor_review_warnings": actor_review_warnings,
        "report_only": True,
        "company_reports": analyses,
        "method_ids": METHOD_IDS,
        "workflow_step_ids": WORKFLOW_STEP_IDS,
        "company_work_queue": company_work_queue,
        "cache_policy": cache_policy_summary,
        "method_coverage": method_coverage,
        "artifact_quality": artifact_quality,
        "run_health": {
            "status": run_health["status"],
            "warning_count": len(run_health["warnings"]),
            "failure_count": len(run_health["failures"]),
            "elapsed_ms": run_health["elapsed_ms"],
            "artifact": "run_health.json",
        },
        "parallel_execution": {
            "max_company_workers": company_worker_count(ctx["config"], len(company_records)),
            "max_stage_workers": bounded_int((ctx["config"].get("internet_research") or {}).get("max_stage_workers"), default=len(RESEARCH_STAGE_IDS), maximum=len(RESEARCH_STAGE_IDS)),
            "max_scoring_workers": scoring_worker_count(ctx["config"]),
            "llm_backpressure": services["llm_limiter"].config_summary(),
            "company_processing_order": [analysis["company_slug"] for analysis in analyses],
        },
        "actor_review": {
            "llm_actor_ids": actor_review_config(ctx["config"])["llm_actor_ids"],
            "max_context_chars": actor_review_config(ctx["config"])["max_context_chars"],
            "context_json_chars": None,
            "prompt_context_json_chars": None,
            "context_compression": {"distributed_by_workflow_step": True},
        },
        "observability": observation_summary,
        "memory_boundary": {
            "rag_knowledge": {
                "storage": "redis_vector_index",
                "purpose": "durable playbook and method knowledge used to do the VC job",
                "namespace": (knowledge_rag.get("config") or {}).get("namespace") if isinstance(knowledge_rag.get("config"), dict) else "",
            },
            "working_memory": {
                "storage": "local_artifacts_and_prompt_context",
                "persist_to_redis": False,
                "purpose": "transient browser/tool observations and actor-review context",
            },
        },
        "monitor_state": {
            "mode": "folder_monitoring",
            "cycles_completed": 1,
            "max_cycles": ctx["max_cycles"],
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "watch_state": read_workflow_state(ctx["run_dir"], "watch_state.json", {}),
        },
        "output_files": output_files,
        "actor_findings": actor_findings,
        "llm_usage": llm_usage(services.get("llm")) if services.get("llm") is not None else {"provider": "none", "model": "none", "calls": 0},
        "action_ledger": action_ledger,
    }
    root_output_files = [
        {"kind": "final_artifact_json", "path": str(ctx["output_folder"] / "final_artifact.json")},
        {"kind": "action_ledger_json", "path": str(ctx["output_folder"] / "action_ledger.json")},
        {"kind": "artifact_quality_json", "path": str(ctx["output_folder"] / "artifact_quality.json")},
        {"kind": "run_health_json", "path": str(ctx["output_folder"] / "run_health.json")},
    ]
    trace_path = ctx["run_dir"] / "llm_rag_trace.jsonl"
    trace_output_path = ctx["output_folder"] / "llm_rag_trace.jsonl"
    if trace_path.exists():
        root_output_files.append({"kind": "llm_rag_trace_jsonl", "path": str(trace_output_path)})
    final_artifact["output_files"] = [*output_files, *root_output_files]
    result = {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "completed", "final_artifact": final_artifact}

    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "human_input_requested", {"mode": "approval_required", "reason": "Reports contain heuristic investment-analysis scores for human review only."})
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    with observed_operation(ctx["run_dir"], phase="writing_artifacts", operation="write_final_outputs", output_file_count=len(final_artifact["output_files"])):
        write_json(ctx["output_folder"] / "final_artifact.json", final_artifact)
        write_json(ctx["output_folder"] / "action_ledger.json", action_ledger)
        write_json(ctx["output_folder"] / "artifact_quality.json", artifact_quality)
        write_json(ctx["output_folder"] / "run_health.json", run_health)
        write_json(ctx["run_dir"] / "result.json", result)
        write_json(ctx["run_dir"] / "final_artifact.json", final_artifact)
        write_json(ctx["run_dir"] / "action_ledger.json", action_ledger)
        write_json(ctx["run_dir"] / "artifact_quality.json", artifact_quality)
        write_json(ctx["run_dir"] / "run_health.json", run_health)
    for path in ("final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json"):
        append_event(ctx["run_dir"], "artifact_written", {"path": str(ctx["output_folder"] / path)})
    append_event(ctx["run_dir"], "artifact_written", {"path": "result.json"})
    append_event(ctx["run_dir"], "artifact_written", {"path": "final_artifact.json"})
    append_event(ctx["run_dir"], "artifact_written", {"path": "action_ledger.json"})
    append_event(ctx["run_dir"], "artifact_written", {"path": "artifact_quality.json"})
    append_event(ctx["run_dir"], "artifact_written", {"path": "run_health.json"})
    if trace_path.exists():
        shutil.copyfile(trace_path, trace_output_path)
        append_event(ctx["run_dir"], "artifact_written", {"path": str(trace_output_path)})
        append_event(ctx["run_dir"], "artifact_written", {"path": "llm_rag_trace.jsonl"})
    complete_runtime_step(ctx, "batch_index_writer", {"output_folder": str(ctx["output_folder"]), "output_file_count": len(final_artifact["output_files"])})
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID})
    write_json(ctx["run_dir"] / "run.json", {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()})
    return step_result(ctx, "batch_index_writer", final_artifact=final_artifact)


def build_step_handlers() -> dict[str, Any]:
    handlers = {
        "startup_folder_watcher": run_startup_folder_watcher_step,
        "company_packet_grouper": run_company_packet_grouper_step,
        "document_evidence_extractor": run_document_evidence_extractor_step,
        "claim_normalizer": run_claim_normalizer_step,
        "research_planner": run_research_planner_step,
        "research_reconciler": run_research_reconciler_step,
        "score_consistency_auditor": run_score_consistency_auditor_step,
        "company_report_writer": run_company_report_writer_step,
        "batch_index_writer": run_batch_index_writer_step,
    }
    for stage in RESEARCH_STAGE_IDS:
        handlers[stage] = lambda ctx, *, llm_client=None, _stage=stage: run_research_stage_step(ctx, _stage, llm_client=llm_client)
    for scorer_stage in SCORER_METHOD_BY_STAGE:
        handlers[scorer_stage] = lambda ctx, *, llm_client=None, _stage=scorer_stage: run_scorer_step(ctx, _stage, llm_client=llm_client)
    return handlers


STEP_HANDLERS = build_step_handlers()



def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    current_run_id = run_id
    final_result: dict[str, Any] | None = None
    for step_id in WORKFLOW_STEP_IDS:
        final_result = run_runtime_step(
            step_id,
            inputs=inputs,
            config=config,
            runs_root=runs_root,
            run_id=current_run_id,
            llm_client=llm_client,
        )
        current_run_id = final_result["run_id"]
    if not final_result or "final_artifact" not in final_result:
        raise RuntimeError("VC Assistant workflow completed without a final artifact.")
    return {
        "run_id": final_result["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": final_result["status"],
        "final_artifact": final_result["final_artifact"],
    }


def run_runtime_step(
    step_id: str,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    step_id = str(step_id or "").strip()
    if step_id not in STEP_HANDLERS:
        raise ValueError(f"Unknown VC Assistant workflow step: {step_id}")
    ctx = runtime_context_for_step(inputs=inputs, config=config, runs_root=runs_root, run_id=run_id)
    benchmark_enabled = benchmark_mode_enabled(ctx["config"])
    debug_enabled = debug_mode_enabled(ctx["config"])
    step_started = time.monotonic()
    if debug_enabled:
        ctx["run_dir"].mkdir(parents=True, exist_ok=True)
        append_debug_record(
            ctx["run_dir"],
            "debug_workflow_step_started",
            {
                "step_id": step_id,
                "run_id": ctx["run_id"],
                "runtime_step_mode": "workflow_step_handler",
                "input_keys": sorted((inputs or {}).keys()),
                "fake_llm": fake_llm_mode_enabled(ctx["config"]),
                "fake_skills": fake_skills_mode_enabled(ctx["config"]),
                "benchmark": benchmark_enabled,
                "debug": True,
            },
        )
    if benchmark_enabled:
        ctx["run_dir"].mkdir(parents=True, exist_ok=True)
        append_event(
            ctx["run_dir"],
            "benchmark_step_started",
            {"step_id": step_id, "runtime_step_mode": "workflow_step_handler"},
        )
    try:
        result = STEP_HANDLERS[step_id](ctx, llm_client=llm_client)
        if debug_enabled:
            append_debug_record(
                ctx["run_dir"],
                "debug_workflow_step_completed",
                {
                    "step_id": step_id,
                    "run_id": ctx["run_id"],
                    "runtime_step_mode": "workflow_step_handler",
                    "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
                    "result_keys": sorted(result.keys()) if isinstance(result, dict) else [],
                    "status": "completed",
                },
            )
        if benchmark_enabled:
            append_event(
                ctx["run_dir"],
                "benchmark_step_completed",
                {
                    "step_id": step_id,
                    "status": "completed",
                    "runtime_step_mode": "workflow_step_handler",
                    "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
                },
            )
            write_benchmark_artifacts(
                ctx["run_dir"],
                run_id=ctx["run_id"],
                status="completed" if "final_artifact" in result else "running",
            )
        return result
    except Exception as exc:
        ctx["run_dir"].mkdir(parents=True, exist_ok=True)
        if debug_enabled:
            append_debug_record(
                ctx["run_dir"],
                "debug_workflow_step_failed",
                {
                    "step_id": step_id,
                    "run_id": ctx["run_id"],
                    "runtime_step_mode": "workflow_step_handler",
                    "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
                    "error": str(exc),
                },
            )
        if benchmark_enabled:
            append_event(
                ctx["run_dir"],
                "benchmark_step_failed",
                {
                    "step_id": step_id,
                    "status": "failed",
                    "runtime_step_mode": "workflow_step_handler",
                    "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
                    "error": str(exc),
                },
            )
            write_benchmark_artifacts(ctx["run_dir"], run_id=ctx["run_id"], status="failed")
        append_event(
            ctx["run_dir"],
            "workflow_step_failed",
            {"step_id": step_id, "runtime_step_mode": "workflow_step_handler", "error": str(exc)},
        )
        write_failed_run(ctx, exc)
        raise

def main() -> None:
    parser = argparse.ArgumentParser(description=BLUEPRINT_NAME)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--force-reprocess", action="store_true")
    args = parser.parse_args()
    inputs: dict[str, Any] = {}
    if args.input_folder:
        inputs["document_folder"] = args.input_folder
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    if args.force_reprocess:
        inputs["force_reprocess"] = True
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
        printable["final_artifact"] = final_artifact_for_transport(result["final_artifact"]) if step_id else result["final_artifact"]
    print(json.dumps(printable, indent=2))


if __name__ == "__main__":
    main()
