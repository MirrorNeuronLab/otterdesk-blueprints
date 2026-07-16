"""VC evidence, claim, truth-discovery, and Bayesian policy."""

from __future__ import annotations

from .common import *
from .intake import slugify
from .research_core import infer_source_quality_label

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
