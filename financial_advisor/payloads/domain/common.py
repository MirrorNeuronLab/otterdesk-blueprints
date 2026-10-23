#!/usr/bin/env python3.12
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from mn_prototype_actor_review_agent.actors import get_actor_llm_client
from mn_sdk.blueprint_support import (
    DeterministicFallbackLLM,
    fake_llm_mode_enabled,
    source_manifest,
    utc_now_iso as utc_now_iso,
)
from mn_sdk_common.prompts import PromptLibrary

try:
    from mn_docs_to_markdown_skill import docker_ocr_client_factory_from_config, extract_document
except Exception:  # pragma: no cover - optional runtime dependency
    docker_ocr_client_factory_from_config = None
    extract_document = None


_SOURCE_MANIFEST = source_manifest(__file__)
BLUEPRINT_ID = _SOURCE_MANIFEST["identity"]["id"]
OUTPUT_TYPE = "financial_advisor_report"
RECOMMENDED_ACTION = "review_integrated_financial_advisor_packet_before_any_financial_action"
OCR_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_SUFFIXES = OCR_SUFFIXES | {".txt", ".json", ".csv", ".md"}
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md"}
OCR_MIN_TEXT_CHARS = 40
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
