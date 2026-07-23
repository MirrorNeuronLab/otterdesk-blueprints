"""Contract clause extraction, playbook comparison, and durable lane operations."""

from __future__ import annotations

from .common import *
from .documents import contract_records
from .state import load_state, save_state

def snippet_around(text: str, keyword: str, width: int = 220) -> str:
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return ""
    start = max(0, index - width // 3)
    end = min(len(text), index + width)
    return " ".join(text[start:end].split())

def clause_locator(record: dict[str, Any], keyword: str) -> str:
    pages = record.get("pages") if isinstance(record.get("pages"), list) else []
    for index, page in enumerate(pages, start=1):
        if isinstance(page, dict):
            page_text = str(page.get("text") or page.get("content") or "")
            page_number = page.get("page_number") or page.get("page") or index
        else:
            page_text = str(page or "")
            page_number = index
        if keyword.lower() in page_text.lower():
            return f"page {page_number}"
    return f"document-level keyword match: {keyword}"

def extract_contract_clause_packet(records: list[dict[str, Any]]) -> dict[str, Any]:
    clauses = []
    for record in contract_records(records):
        text = str(record.get("text") or "")
        for field in CLAUSE_FIELDS:
            keyword = field.replace("_", " ")
            snippet = snippet_around(text, keyword)
            if not snippet and field == "liability":
                snippet = snippet_around(text, "limitation of liability")
            if not snippet and field == "indemnity":
                snippet = snippet_around(text, "indemn")
            if snippet:
                clauses.append(
                    {
                        "source": record.get("filename"),
                        "source_ref": record.get("filename"),
                        "clause_type": field,
                        "status": "present",
                        "locator": clause_locator(record, keyword),
                        "text": snippet,
                        "observed_language": snippet,
                        "confidence": 0.78,
                        "review_notes": ["Attorney review required before relying on this classification."],
                    }
                )
    clause_types = sorted({clause["clause_type"] for clause in clauses})
    return {
        "schema_version": "mn.blueprint.legal_assistant.contract_clause_review.v1",
        "contract_count": len(contract_records(records)),
        "clause_count": len(clauses),
        "clause_types": clause_types,
        "clauses": clauses,
        "playbook_comparison": compare_to_playbook(clause_types),
        "review_required": True,
    }

def compare_to_playbook(clause_types: list[str]) -> dict[str, Any]:
    required = {"governing_law", "assignment", "indemnity", "termination", "liability"}
    present = set(clause_types)
    missing = sorted(required - present)
    deviations = []
    if "liability" in present:
        deviations.append("Confirm liability cap, exclusions, and indirect damages language with counsel.")
    if "assignment" in present:
        deviations.append("Check whether assignment restrictions affect transfers, affiliates, or change-of-control events.")
    if "indemnity" in present:
        deviations.append("Confirm indemnity scope, covered claims, defense control, exclusions, and survival with counsel.")
    if "termination" in present:
        deviations.append("Check termination triggers, cure periods, payment consequences, and post-termination obligations.")
    return {
        "required_clause_types": sorted(required),
        "present_required_clause_types": sorted(required & present),
        "missing_required_clause_types": missing,
        "deviations": deviations,
        "status": "needs_attorney_review" if missing or deviations else "review_ready",
    }


def extract_contracts(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    packet = extract_contract_clause_packet(state.get("records") or [])
    state["clause_packet"] = packet
    save_state(ctx, state, "legal_contract_lane.json")
    return {"clause_count": packet.get("clause_count", 0)}


def compare_contracts(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    packet = state.get("clause_packet") or extract_contract_clause_packet(state.get("records") or [])
    clause_types = [str(item.get("clause_type")) for item in packet.get("clauses") or [] if isinstance(item, dict)]
    comparison = compare_to_playbook(clause_types)
    state["playbook_comparison"] = comparison
    save_state(ctx, state, "legal_contract_lane.json")
    return {"comparison": comparison}


__all__ = ["compare_contracts", "extract_contracts"]
