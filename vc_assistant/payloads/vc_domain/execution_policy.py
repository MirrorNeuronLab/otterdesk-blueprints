"""VC-specific bounded worker and scoring-profile policy."""

from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import bounded_int

from .common import FUND_PROFILE_WEIGHTS, METHOD_IDS


def scoring_worker_count(config: dict[str, Any]) -> int:
    scoring = config.get("scoring") if isinstance(config.get("scoring"), dict) else {}
    return bounded_int(
        scoring.get("max_workers"), default=7, maximum=len(METHOD_IDS)
    )


def scoring_fund_profile(config: dict[str, Any]) -> str:
    scoring = config.get("scoring") if isinstance(config.get("scoring"), dict) else {}
    raw = str(
        scoring.get("fund_profile") or config.get("fund_profile") or "generalist"
    ).strip().lower().replace("-", "_")
    return raw if raw in FUND_PROFILE_WEIGHTS else "generalist"


def company_worker_count(config: dict[str, Any], company_count: int) -> int:
    execution = (
        config.get("execution") if isinstance(config.get("execution"), dict) else {}
    )
    return bounded_int(
        execution.get("max_company_workers"),
        default=min(4, max(1, company_count)),
        maximum=max(1, company_count),
    )


__all__ = ["company_worker_count", "scoring_fund_profile", "scoring_worker_count"]
