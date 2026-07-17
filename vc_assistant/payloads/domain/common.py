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

from mn_sdk import resolve_blueprint_path, resolve_bundle_path
from mn_sdk.blueprint_support import BlueprintBundleLayout

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
    load_runtime_config,
    persist_blueprint_run_context,
    read_json_object as read_json,
    read_workflow_state,
    resolve_existing_path,
    source_manifest,
    source_workflow_steps,
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
    group_document_file_records as shared_group_document_file_records,
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

_SOURCE_MANIFEST = source_manifest(__file__)
_DEFAULT_CONFIG = load_runtime_config(__file__)
_IDENTITY = (
    _SOURCE_MANIFEST.get("identity")
    if isinstance(_SOURCE_MANIFEST.get("identity"), dict)
    else {}
)
_DOCUMENT_AUTOMATION = (
    _DEFAULT_CONFIG.get("document_automation")
    if isinstance(_DEFAULT_CONFIG.get("document_automation"), dict)
    else {}
)
_INPUT_PAYLOAD = (
    (_DEFAULT_CONFIG.get("inputs") or {}).get("payload")
    if isinstance(_DEFAULT_CONFIG.get("inputs"), dict)
    and isinstance((_DEFAULT_CONFIG.get("inputs") or {}).get("payload"), dict)
    else {}
)
_PUBLIC_DATASET = (
    _INPUT_PAYLOAD.get("public_dataset")
    if isinstance(_INPUT_PAYLOAD.get("public_dataset"), dict)
    else {}
)

BLUEPRINT_ID = str(_IDENTITY.get("id") or "").strip()
BLUEPRINT_NAME = str(_IDENTITY.get("name") or "").strip()
OUTPUT_TYPE = str(_DOCUMENT_AUTOMATION.get("output_type") or "").strip()
RECOMMENDED_ACTION = str(
    _DOCUMENT_AUTOMATION.get("recommended_action") or ""
).strip()

if not all((BLUEPRINT_ID, BLUEPRINT_NAME, OUTPUT_TYPE, RECOMMENDED_ACTION)):
    raise RuntimeError(
        "VC manifest identity and default document_automation contract are required"
    )

SUPPORTED_SUFFIXES = {
    suffix
    for item in _PUBLIC_DATASET.get("expected_files") or []
    for suffix in [str(item).strip().removeprefix("*").lower()]
    if suffix.startswith(".")
}
if not SUPPORTED_SUFFIXES:
    raise RuntimeError("VC default input public_dataset.expected_files is required")
TEXT_SUFFIXES = SUPPORTED_SUFFIXES - {".pdf"}

WORKFLOW_STEPS = source_workflow_steps(__file__)

WORKFLOW_STEP_IDS = [str(step["id"]) for step in WORKFLOW_STEPS]

_AGENT_REGISTRY = (
    (_SOURCE_MANIFEST.get("agents") or {}).get("registry")
    if isinstance(_SOURCE_MANIFEST.get("agents"), dict)
    and isinstance((_SOURCE_MANIFEST.get("agents") or {}).get("registry"), dict)
    else {}
)
AGENT_IDS = list(_AGENT_REGISTRY)
RESEARCH_AGENT_IDS = [
    agent_id
    for agent_id, definition in _AGENT_REGISTRY.items()
    if isinstance(definition, dict)
    and definition.get("handler") == "agents.public_researcher"
]
SCORER_AGENT_BY_METHOD = {
    str(parameters["method"]): agent_id
    for agent_id, definition in _AGENT_REGISTRY.items()
    if isinstance(definition, dict)
    and isinstance((parameters := definition.get("with")), dict)
    and str(parameters.get("method") or "").strip()
}
METHOD_IDS = list(SCORER_AGENT_BY_METHOD)

_INTERNET_RESEARCH_DEFAULTS = (
    _DEFAULT_CONFIG.get("internet_research")
    if isinstance(_DEFAULT_CONFIG.get("internet_research"), dict)
    else {}
)
DEFAULT_RESEARCH_SOURCE_URLS = list(
    _INTERNET_RESEARCH_DEFAULTS.get("default_source_urls") or []
)
DEFAULT_VERIFICATION_DOMAINS = list(
    _INTERNET_RESEARCH_DEFAULTS.get("verification_domains") or []
)
DEFAULT_SOURCE_URL_TEMPLATES = list(
    _INTERNET_RESEARCH_DEFAULTS.get("source_url_templates") or []
)

WebBrowserConfig = None

browse = None

research_topic = None

docker_ocr_client_factory_from_config = None

extract_document_folder = None

EVENT_LOCK = threading.Lock()

TRACE_LOCK = threading.Lock()

SKILL_LOAD_LOCK = threading.Lock()

NON_SUBSTANTIVE_SOURCE_STATUSES = {
    "planned",
    "configured_reference",
    "disabled",
    "skill_unavailable",
    "failed",
    "blocked",
    "warning",
    "error",
    "budget_exhausted",
    "mocked",
}

WARNING_SOURCE_STATUSES = {"failed", "blocked", "skill_unavailable", "warning", "budget_exhausted"}

DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS = 10.0

_ACTOR_REVIEW_DEFAULTS = (
    _DEFAULT_CONFIG.get("actor_review")
    if isinstance(_DEFAULT_CONFIG.get("actor_review"), dict)
    else {}
)
DEFAULT_ACTOR_REVIEW_LLM_ACTOR_IDS = list(
    _ACTOR_REVIEW_DEFAULTS.get("llm_actor_ids") or []
)
DEFAULT_ACTOR_REVIEW_CONTEXT_TARGET_TOKENS = int(
    _ACTOR_REVIEW_DEFAULTS.get("context_target_tokens") or 0
)
DEFAULT_ACTOR_REVIEW_CONTEXT_TOKEN_BUDGET = int(
    _ACTOR_REVIEW_DEFAULTS.get("context_token_budget") or 0
)

MAX_TRANSPORT_EVIDENCE_PER_COMPANY = 20

MAX_TRANSPORT_SOURCES_PER_COMPANY = 80

MAX_TRANSPORT_SNIPPET_CHARS = 1200

MAX_TRANSPORT_TEXT_PREVIEW_CHARS = 600

_KNOWLEDGE_RAG_DESCRIPTOR = (
    _SOURCE_MANIFEST.get("knowledge_rag")
    if isinstance(_SOURCE_MANIFEST.get("knowledge_rag"), dict)
    else {}
)
_KNOWLEDGE_RELATIVE_DIR = Path(
    str(_KNOWLEDGE_RAG_DESCRIPTOR.get("knowledge_dir") or "knowledge")
)
_KNOWLEDGE_LAYOUT = BlueprintBundleLayout.discover(__file__, require_manifest=True)
_KNOWLEDGE_DIRECTORY = resolve_bundle_path(
    str(_KNOWLEDGE_RELATIVE_DIR),
    bundle_root=_KNOWLEDGE_LAYOUT.root,
    payload_root=_KNOWLEDGE_LAYOUT.payload_root,
)
_KNOWLEDGE_DOCUMENTS = sorted(
    _KNOWLEDGE_DIRECTORY.glob("*.md")
)
if len(_KNOWLEDGE_DOCUMENTS) != 1:
    raise RuntimeError("VC knowledge_rag.knowledge_dir must contain one Markdown playbook")
KNOWLEDGE_PLAYBOOK_RELATIVE_PATH = str(
    _KNOWLEDGE_DIRECTORY.relative_to(_KNOWLEDGE_LAYOUT.payload_root)
    / _KNOWLEDGE_DOCUMENTS[0].name
)

_AGENTIC_RESEARCH_DEFAULTS = (
    _SOURCE_MANIFEST.get("agentic_research")
    if isinstance(_SOURCE_MANIFEST.get("agentic_research"), dict)
    else {}
)
DEFAULT_AGENTIC_RESEARCH_AGENT_IDS = list(
    _AGENTIC_RESEARCH_DEFAULTS.get("agent_ids") or []
)
DEFAULT_AGENTIC_RESEARCH_TOOLS = list(
    _AGENTIC_RESEARCH_DEFAULTS.get("allowed_tools") or []
)

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
