#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-litellm-communicate-skill",
    "mirrorneuron-llm-ocr-skill",
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
    DeterministicFallbackLLM,
    PromptLibrary,
    append_event_jsonl,
    fake_llm_mode_enabled,
    get_actor_llm_client,
    load_resolved_config as load_shared_resolved_config,
    start_agent_beacon_thread,
)
from mn_sdk.blueprint_support import source_manifest

try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document
except Exception:  # pragma: no cover - optional runtime dependency
    docker_ocr_client_factory_from_config = None
    extract_document = None


BLUEPRINT_ID = "financial_advisor"
BLUEPRINT_NAME = "Financial Advisor"
OUTPUT_TYPE = "financial_advisor_report"
RECOMMENDED_ACTION = "review_integrated_financial_advisor_packet_before_any_financial_action"
OCR_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_SUFFIXES = OCR_SUFFIXES | {".txt", ".json", ".csv", ".md"}
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md"}
OCR_MIN_TEXT_CHARS = 40
HEAVY_MODEL_STEPS = {
    "tax_workpaper_preparer",
    "tax_llm_reviewer",
    "portfolio_risk_engine",
    "portfolio_llm_reviewer",
    "advisor_review_auditor",
    "financial_advice_reporter",
}
_SOURCE_MANIFEST = source_manifest(__file__)


def _source_workflow_step_specs() -> list[dict[str, Any]]:
    workflow = _SOURCE_MANIFEST.get("workflow") if isinstance(_SOURCE_MANIFEST.get("workflow"), dict) else {}
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    return [step for step in steps if isinstance(step, dict)]


def _source_agent_ids() -> list[str]:
    agents = _SOURCE_MANIFEST.get("agents") if isinstance(_SOURCE_MANIFEST.get("agents"), dict) else {}
    registry = agents.get("registry") if isinstance(agents.get("registry"), dict) else {}
    return [str(agent_id) for agent_id in registry]


WORKFLOW_STEPS = [str(step["id"]) for step in _source_workflow_step_specs()]
WORKFLOW_STEP_IDS = WORKFLOW_STEPS
AGENT_IDS = _source_agent_ids()
OUTPUT_MESSAGE_BY_AGENT = {agent_id: f"{agent_id}_completed" for agent_id in AGENT_IDS}
DEFAULT_MARKET_PRICES = {
    "SPY": 500.0,
    "AGG": 100.0,
    "GLD": 200.0,
    "BND": 74.0,
    "QQQ": 430.0,
    "VTI": 260.0,
}
RISK_BY_ASSET_CLASS = {
    "cash": 0.01,
    "rates": 0.05,
    "bond": 0.06,
    "fixed_income": 0.06,
    "commodity": 0.14,
    "equity": 0.18,
    "crypto": 0.65,
    "other": 0.22,
}
KNOWN_ETF_SYMBOLS = {
    "AGG",
    "BND",
    "GLD",
    "QQQ",
    "SPY",
    "VTI",
}
TAX_METADATA_FIELDS = {
    "source_dataset",
    "source_row",
    "label",
    "class",
    "form_type",
    "tax_form_type",
}
TAX_READINESS_LABELS = {
    "identified_only": "Identified",
    "extracted": "Extracted",
    "reconciled": "Reconciled",
    "complete": "Complete",
}
INVESTMENT_PROFILE_FIELDS = (
    "account_purpose",
    "investment_objective",
    "time_horizon",
    "expected_withdrawal_date",
    "risk_tolerance",
    "liquidity_needs",
    "tax_objective",
    "amount_that_must_remain_liquid",
    "other_investment_accounts",
    "tax_consequences_of_selling",
)
PUBLIC_GUIDANCE_SOURCES = [
    {
        "title": "Consumer.gov managing your money",
        "url": "https://consumer.gov/managing-your-money",
        "topic": "budget and cash-flow review",
    },
    {
        "title": "Consumer Financial Protection Bureau bank accounts",
        "url": "https://www.consumerfinance.gov/consumer-tools/bank-accounts/",
        "topic": "bank statements, fees, and account review",
    },
    {
        "title": "IRS records you should keep",
        "url": "https://www.irs.gov/businesses/small-businesses-self-employed/recordkeeping",
        "topic": "tax record organization",
    },
    {
        "title": "Investor.gov risk tolerance",
        "url": "https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/assessing-risk",
        "topic": "portfolio risk education",
    },
]
KNOWLEDGE_PLAYBOOK_RELATIVE_PATH = "knowledge/financial_advisor_playbook.md"
FINANCIAL_JUDGE_RUBRIC = [
    "method_correctness",
    "evidence_traceability",
    "calculation_invariance",
    "assumption_clarity",
    "missing_evidence_honesty",
    "risk_interpretation_quality",
    "review_only_language",
    "actionability_without_unauthorized_action",
]
KNOWLEDGE_SECTIONS_BY_STEP = {
    "cash_flow_llm_analyst": ("bank statement", "cash-flow", "evidence hierarchy", "report quality"),
    "tax_workpaper_preparer": ("tax", "tax form", "evidence hierarchy", "report quality"),
    "tax_llm_reviewer": ("tax", "tax form", "evidence hierarchy", "report quality"),
    "portfolio_risk_engine": ("portfolio", "risk", "evidence hierarchy", "report quality"),
    "portfolio_llm_reviewer": ("portfolio", "risk", "evidence hierarchy", "report quality"),
    "advisor_review_auditor": ("reconciliation", "audit", "evidence hierarchy", "report quality"),
    "financial_advice_reporter": ("report quality", "reconciliation", "review boundary", "evidence hierarchy"),
}
REVIEW_PROMPT_FILES = {
    "cash_flow_llm_analyst": "cash-flow-llm-review.md",
    "tax_llm_reviewer": "tax-llm-review.md",
    "portfolio_llm_reviewer": "portfolio-llm-review.md",
}
PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)

class DeterministicLLM(DeterministicFallbackLLM):
    def __init__(self) -> None:
        super().__init__(
            "deterministic-financial-advisor",
            default_summary="Deterministic review packet generated from local evidence.",
            confidence=0.74,
        )

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False, default=str) + "\n", encoding="utf-8")

def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")

def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    append_event_jsonl(run_dir, event_type, redact_value(payload))

def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result

def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value[:50]]
    if isinstance(value, str):
        text = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", value)
        text = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED-CARD]", text)
        text = re.sub(r"\b\d{9,18}\b", "[REDACTED-ID]", text)
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", text)
        return text[:1000]
    return value
