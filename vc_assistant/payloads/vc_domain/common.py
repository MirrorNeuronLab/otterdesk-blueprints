"""Shared imports and immutable VC policy constants."""

from dataclasses import asdict, dataclass

import hashlib

import json

import os

import re

import threading

import time

import uuid

from concurrent.futures import ThreadPoolExecutor, as_completed

from functools import partial

from pathlib import Path

from typing import Any

from urllib.parse import urlparse

from mn_blueprint_support import (
    PromptLibrary,
    append_event_jsonl,
    env_flag_enabled,
    fake_llm_mode_enabled,
    fake_skills_mode_enabled,
    get_actor_llm_client,
    resolve_actor_specs,
)

from mn_sdk.blueprint_support import (
    ActionBudget,
    BudgetedLlmClient,
    LlmCallLimiter,
    ObservedOperation,
    WorkflowStateStore,
    bounded_int,
    build_action_budget,
    build_llm_call_limiter as build_shared_llm_call_limiter,
    call_with_supported_kwargs,
    create_blueprint_run_context,
    debug_mode_enabled,
    expand_runtime_path,
    persist_blueprint_run_context,
    read_json_object as read_json,
    read_workflow_state,
    resolve_existing_path,
    source_workflow_steps,
    source_manifest_path,
    observed_operation as shared_observed_operation,
    redact_observation_value,
    utc_now_iso,
    workflow_state_file,
    write_failed_run,
    write_benchmark_artifacts as write_shared_benchmark_artifacts,
    write_json,
    write_workflow_state,
)

from mn_prototype_bounded_tool_loop_agent import (
    ToolAction,
    ToolLoopSpec,
    ToolPlan,
    create_agent as create_bounded_tool_loop,
)

from mn_prototype_actor_review_agent import (
    ActorReviewResult,
    ActorReviewSpec,
    create_agent as create_actor_review,
)

def build_llm_call_limiter(config: dict[str, Any]) -> LlmCallLimiter:
    return build_shared_llm_call_limiter(config, fake_mode=fake_llm_mode_enabled(config))

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
    build_artifact_quality_report as shared_build_artifact_quality_report,
    build_research_coverage as shared_build_research_coverage,
    build_run_health_report as shared_build_run_health_report,
    markdown_cell,
    quality_check as shared_quality_check,
)

from mn_document_reading_skill import (
    document_paths as shared_document_paths,
    file_sha256,
    infer_group_name,
    redact_common_pii,
    records_fingerprint,
    safe_read_text,
)

from mn_rag_skill import (
    KnowledgeRagSession,
    knowledge_rag_config as skill_knowledge_rag_config,
    prepare_blueprint_knowledge_rag as skill_prepare_blueprint_knowledge_rag,
    public_rag_state as skill_public_rag_state,
    require_ready_knowledge_rag as skill_require_ready_knowledge_rag,
    resolve_blueprint_knowledge_dir as skill_resolve_blueprint_knowledge_dir,
    retrieve_knowledge_rag_context as skill_retrieve_knowledge_rag_context,
)

from mn_public_research_orchestrator_skill import (
    annotate_agent_sources as shared_annotate_agent_sources,
    append_python_http_search as shared_append_python_http_search,
    append_python_http_targets as shared_append_python_http_targets,
    budget_exhausted_source as shared_budget_exhausted_source,
    compact_company_report_for_transport as shared_compact_company_report_for_transport,
    compact_local_evidence_for_transport as shared_compact_local_evidence_for_transport,
    compact_research_sources_for_transport as shared_compact_research_sources_for_transport,
    compact_text as shared_compact_text,
    dedupe_list,
    extract_domains,
    fetch_public_http as shared_fetch_public_http,
    host_from_url,
    lane as shared_lane,
    observation_from_sources as shared_observation_from_sources,
    flatten_research_ledger as flattened_sources,
    normalize_research_ledger as shared_normalize_research_ledger,
    PublicResearchPolicy,
    PublicResearchToolset,
    source_record as shared_source_record,
)

from mn_scoring_framework_skill import (
    audit_method_scores as shared_audit_method_scores,
    build_method_coverage as shared_build_method_coverage,
    evidence_status,
    keyword_score,
    money_values,
    method_result as shared_method_result,
    run_scorers,
    source_refs_from_records,
    source_refs_from_sources,
)

_fetch_public_http = partial(
    shared_fetch_public_http,
    default_user_agent="MirrorNeuron-VC-Assistant/1.0 (+public research fallback)",
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

WORKFLOW_STEPS = source_workflow_steps(__file__)

WORKFLOW_STEP_IDS = [str(step["id"]) for step in WORKFLOW_STEPS]

_SOURCE_MANIFEST = read_json(source_manifest_path(__file__))

AGENT_IDS = list(((_SOURCE_MANIFEST.get("agents") or {}).get("registry") or {}))

RESEARCH_AGENT_IDS = [
    "company_identity_researcher",
    "funding_researcher",
    "market_comp_researcher",
    "traction_verifier",
    "rendered_page_researcher",
]

SCORER_AGENT_BY_METHOD = {
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

try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document_folder
except Exception:  # pragma: no cover - optional runtime support
    docker_ocr_client_factory_from_config = None
    extract_document_folder = None

# Export private dependency aliases as well as public constants to domain modules.
__all__ = [name for name in globals() if not name.startswith("__")]
