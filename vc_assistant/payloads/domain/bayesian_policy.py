"""VC-owned Bayesian claim templates and evidence interpretation policy."""

from __future__ import annotations

from .common import *


_SOURCE_LIKELIHOODS = {
    "true": {"high": 0.90, "medium": 0.75, "low": 0.60},
    "false": {"high": 0.35, "medium": 0.25, "low": 0.12},
}

VC_BAYESIAN_NETWORK_SPECS = {
    "revenue_claim": {
        "template_id": "revenue_claim",
        "evidence_variables": [
            "FounderEvidenceObserved",
            "InvoiceFound",
            "CustomerContractFound",
            "BankDepositFound",
            "ContradictionFound",
        ],
        "independent_variables": [
            "InvoiceFound",
            "CustomerContractFound",
            "BankDepositFound",
        ],
        "source_dependent_variable": "FounderEvidenceObserved",
        "source_likelihoods": _SOURCE_LIKELIHOODS,
        "contradiction_variable": "ContradictionFound",
        "likelihoods": {
            "InvoiceFound": {"true": 0.72, "false": 0.03},
            "CustomerContractFound": {"true": 0.68, "false": 0.04},
            "BankDepositFound": {"true": 0.64, "false": 0.02},
            "ContradictionFound": {"true": 0.08, "false": 0.65},
        },
    },
    "customer_traction_claim": {
        "template_id": "customer_traction_claim",
        "evidence_variables": [
            "FounderEvidenceObserved",
            "CustomerReferenceFound",
            "CustomerCaseStudyFound",
            "ContractFound",
            "UsageDataFound",
            "ContradictionFound",
        ],
        "independent_variables": [
            "CustomerReferenceFound",
            "CustomerCaseStudyFound",
            "ContractFound",
            "UsageDataFound",
        ],
        "source_dependent_variable": "FounderEvidenceObserved",
        "source_likelihoods": _SOURCE_LIKELIHOODS,
        "contradiction_variable": "ContradictionFound",
        "likelihoods": {
            "CustomerReferenceFound": {"true": 0.55, "false": 0.08},
            "CustomerCaseStudyFound": {"true": 0.50, "false": 0.06},
            "ContractFound": {"true": 0.62, "false": 0.04},
            "UsageDataFound": {"true": 0.60, "false": 0.05},
            "ContradictionFound": {"true": 0.08, "false": 0.65},
        },
    },
    "product_claim": {
        "template_id": "product_claim",
        "evidence_variables": [
            "FounderEvidenceObserved",
            "DemoObserved",
            "GithubRepoFound",
            "TechnicalDocsFound",
            "CustomerUsageObserved",
            "ContradictionFound",
        ],
        "independent_variables": [
            "DemoObserved",
            "GithubRepoFound",
            "TechnicalDocsFound",
            "CustomerUsageObserved",
        ],
        "source_dependent_variable": "FounderEvidenceObserved",
        "source_likelihoods": _SOURCE_LIKELIHOODS,
        "contradiction_variable": "ContradictionFound",
        "likelihoods": {
            "DemoObserved": {"true": 0.70, "false": 0.08},
            "GithubRepoFound": {"true": 0.45, "false": 0.10},
            "TechnicalDocsFound": {"true": 0.50, "false": 0.10},
            "CustomerUsageObserved": {"true": 0.58, "false": 0.05},
            "ContradictionFound": {"true": 0.08, "false": 0.65},
        },
    },
}

VC_BAYESIAN_EVIDENCE_LABELS = {
    "FounderEvidenceObserved": "founder/company evidence supports the claim",
    "InvoiceFound": "invoice evidence was found",
    "CustomerContractFound": "customer contract evidence was found",
    "BankDepositFound": "bank deposit/payment evidence was found",
    "CustomerReferenceFound": "customer reference evidence was found",
    "CustomerCaseStudyFound": "customer case study evidence was found",
    "ContractFound": "contract evidence was found",
    "UsageDataFound": "usage/deployment data was found",
    "DemoObserved": "demo or prototype evidence was found",
    "GithubRepoFound": "code repository evidence was found",
    "TechnicalDocsFound": "technical documentation evidence was found",
    "CustomerUsageObserved": "customer usage evidence was found",
    "ContradictionFound": "contradicting evidence was found",
}

VC_BAYESIAN_MISSING_LABELS = {
    key: value.replace(" was found", " was not found").replace(" supports", " does not support")
    for key, value in VC_BAYESIAN_EVIDENCE_LABELS.items()
    if key != "ContradictionFound"
}


def build_vc_bayesian_claim_explanations(
    *,
    company_name: str,
    claims: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    source_reliability_by_id: dict[str, float] | None = None,
    claim_type_priors: dict[str, float] | None = None,
    critical_claim_types: set[str] | None = None,
    min_importance: int = 80,
    max_claims: int = 5,
) -> list[dict[str, Any]]:
    evidence_by_id = {
        str(item.get("evidence_id")): item for item in evidence_items if item.get("evidence_id")
    }
    sources_by_id = {
        str(source.get("source_id")): source for source in sources if source.get("source_id")
    }
    critical = critical_claim_types or VC_BAYESIAN_CRITICAL_CLAIM_TYPES
    selected = [
        claim
        for claim in claims
        if _template_id_for_claim_type(str(claim.get("claim_type") or ""))
        and _is_critical_claim(str(claim.get("claim_type") or ""), critical)
        and int(claim.get("importance") or 0) >= min_importance
    ]
    selected.sort(
        key=lambda claim: (
            int(claim.get("importance") or 0),
            int(claim.get("net_confidence") or 0),
        ),
        reverse=True,
    )
    explanations = []
    for claim in selected[:max_claims]:
        template_id = _template_id_for_claim_type(str(claim.get("claim_type") or ""))
        template = build_bayesian_network(VC_BAYESIAN_NETWORK_SPECS[template_id])
        claim_evidence = [
            evidence_by_id[str(evidence_id)]
            for evidence_id in claim.get("evidence_ids") or []
            if str(evidence_id) in evidence_by_id
        ]
        observations = _observations_from_vc_evidence(
            template_id, claim_evidence, sources_by_id
        )
        reliability = _average_source_reliability(
            claim_evidence, source_reliability_by_id or {}
        )
        claim_with_prior = {
            **claim,
            "prior_probability": float(
                claim.get("prior_probability")
                or claim_type_prior(
                    str(claim.get("claim_type") or ""),
                    claim_type_priors=claim_type_priors,
                )
            ),
        }
        explanation = explain_claim_inference(
            entity_label=company_name,
            claim=claim_with_prior,
            template=template,
            observations=observations,
            source_reliable_prior=source_reliability_prior_tuple(reliability),
            evidence_labels=VC_BAYESIAN_EVIDENCE_LABELS,
            missing_labels=VC_BAYESIAN_MISSING_LABELS,
            interpretation_resolver=_investor_interpretation,
        ).model_dump()
        explanation["investor_interpretation"] = explanation.pop("interpretation", "")
        explanations.append(explanation)
    return explanations


def _template_id_for_claim_type(claim_type: str) -> str | None:
    value = claim_type.lower()
    if value.startswith("traction.revenue") or value in {
        "finance.round_terms",
        "finance.burn",
        "finance.runway",
    }:
        return "revenue_claim"
    if value.startswith((
        "traction.paid",
        "traction.pilot",
        "traction.enterprise",
        "traction.retention",
        "traction.pipeline",
        "traction.users",
        "traction.live",
    )):
        return "customer_traction_claim"
    if value.startswith("product.") or value.startswith("moat.proprietary_dataset"):
        return "product_claim"
    return None


def _is_critical_claim(claim_type: str, critical: set[str]) -> bool:
    return claim_type in critical or any(
        claim_type.startswith(f"{item}.") for item in critical
    )


def _observations_from_vc_evidence(
    template_id: str,
    evidence_items: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> BayesianClaimObservations:
    observations = BayesianClaimObservations(template_id=template_id)
    for evidence in evidence_items:
        evidence_id = str(evidence.get("evidence_id") or "")
        source = sources_by_id.get(str(evidence.get("source_id") or "")) or {}
        source_type = str(source.get("source_type") or evidence.get("source_type") or "")
        text = f"{evidence.get('raw_excerpt') or ''} {evidence.get('claim_text') or ''} {source.get('title') or ''}".lower()
        polarity = str(evidence.get("polarity") or "")
        if polarity == "contradicts":
            observations.mark("ContradictionFound", evidence_id)
            continue
        if polarity != "supports":
            continue
        if source_type in {
            "founder_document",
            "founder_provided_document",
            "company_website",
            "public_profile",
            "data_room_document",
        }:
            observations.mark("FounderEvidenceObserved", evidence_id)
        if template_id == "revenue_claim":
            if source_type == "invoice" or "invoice" in text:
                observations.mark("InvoiceFound", evidence_id)
            if source_type == "customer_contract" or "contract" in text:
                observations.mark("CustomerContractFound", evidence_id)
            if source_type == "data_room_document" and any(
                term in text for term in ("bank", "deposit", "wire", "stripe", "payment")
            ):
                observations.mark("BankDepositFound", evidence_id)
        elif template_id == "customer_traction_claim":
            if source_type in {"customer_case_study", "press_article"} or "case study" in text:
                observations.mark("CustomerCaseStudyFound", evidence_id)
            if source_type == "customer_contract" or "contract" in text:
                observations.mark("ContractFound", evidence_id)
            if any(term in text for term in ("reference", "testimonial", "customer quote")):
                observations.mark("CustomerReferenceFound", evidence_id)
            if any(term in text for term in ("usage", "active user", "deployed", "retention")):
                observations.mark("UsageDataFound", evidence_id)
        else:
            if any(term in text for term in ("demo", "prototype", "working product")):
                observations.mark("DemoObserved", evidence_id)
            if "github" in text or "gitlab" in text:
                observations.mark("GithubRepoFound", evidence_id)
            if any(term in text for term in ("api docs", "architecture", "whitepaper")):
                observations.mark("TechnicalDocsFound", evidence_id)
            if source_type == "customer_case_study" or any(
                term in text for term in ("customer usage", "production", "deployed", "live users")
            ):
                observations.mark("CustomerUsageObserved", evidence_id)
    return observations


def _average_source_reliability(
    evidence_items: list[dict[str, Any]], source_reliability_by_id: dict[str, float]
) -> float:
    values = [
        float(source_reliability_by_id[str(item.get("source_id"))])
        for item in evidence_items
        if str(item.get("source_id")) in source_reliability_by_id
    ]
    return sum(values) / len(values) if values else 0.50


def _investor_interpretation(inference: Any) -> str:
    posterior = inference.claim_true_probability
    if inference.contradiction_found:
        return "Conflicting evidence is present. Resolve it before relying on this claim."
    if posterior >= 0.75 and inference.independent_verification_found:
        return "Strongly supported, but still verify if the claim is investment-critical."
    if posterior >= 0.50:
        return "Plausible but not fully verified. Request stronger source evidence."
    if posterior >= 0.30:
        return "Weakly supported. Treat as unverified until diligence confirms it."
    return "Not reliable based on current evidence."
