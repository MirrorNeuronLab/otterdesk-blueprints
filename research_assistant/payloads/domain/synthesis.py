"""Bounded evidence digests and hypothesis-to-source traceability."""

from __future__ import annotations

import re
from typing import Any


_STOP_WORDS = {
    "about", "after", "against", "also", "between", "could", "each", "from",
    "have", "into", "more", "should", "than", "that", "their", "these", "this",
    "those", "through", "under", "using", "when", "where", "which", "with", "would",
}


def source_catalog(
    documents: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for item in documents:
        if item.get("status") != "extracted" or not str(item.get("text") or "").strip():
            continue
        source_ref = str(item.get("source_ref") or "").strip()
        if not source_ref:
            continue
        catalog[source_ref] = {
            "source_ref": source_ref,
            "title": str(item.get("name") or source_ref),
            "kind": "local_document",
            "status": str(item.get("status") or "unknown"),
            "text": str(item.get("text") or ""),
        }
    for item in sources:
        if item.get("status") != "observed":
            continue
        source_ref = str(item.get("source_ref") or "").strip()
        if not source_ref:
            continue
        catalog[source_ref] = {
            "source_ref": source_ref,
            "title": str(item.get("title") or item.get("url") or source_ref),
            "kind": "public_source",
            "status": str(item.get("status") or "unknown"),
            "text": str(item.get("snippet") or ""),
        }
    return catalog


def evidence_digest(
    documents: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    max_chars: int = 12000,
    per_source_chars: int = 2200,
) -> list[dict[str, Any]]:
    """Return bounded source content for synthesis, not for public queries."""
    digest: list[dict[str, Any]] = []
    remaining = max(1000, max_chars)
    for item in source_catalog(documents, sources).values():
        if remaining <= 0:
            break
        excerpt = item["text"][: min(per_source_chars, remaining)]
        digest.append(
            {
                "source_ref": item["source_ref"],
                "title": item["title"],
                "kind": item["kind"],
                "status": item["status"],
                "excerpt": excerpt,
            }
        )
        remaining -= len(excerpt)
    return digest


def normalize_source_refs(value: Any, valid_refs: set[str]) -> list[str]:
    raw = value if isinstance(value, (list, tuple, set)) else [value] if value else []
    return list(
        dict.fromkeys(str(item).strip() for item in raw if str(item).strip() in valid_refs)
    )


def evidence_links_for_hypothesis(
    hypothesis: dict[str, Any],
    documents: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    limit: int = 4,
) -> tuple[list[str], list[dict[str, Any]]]:
    catalog = source_catalog(documents, sources)
    valid_refs = set(catalog)
    explicit = normalize_source_refs(hypothesis.get("evidence_support"), valid_refs)
    query = " ".join(
        str(hypothesis.get(key) or "") for key in ("statement", "prediction")
    )
    terms = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_+-]+", query)
        if len(token) > 3 and token.lower() not in _STOP_WORDS
    }
    scored: list[tuple[int, str, list[str]]] = []
    for source_ref, item in catalog.items():
        haystack = f"{item['title']} {item['text']}".lower()
        matched = sorted(term for term in terms if term in haystack)
        if matched:
            scored.append((len(matched), source_ref, matched[:8]))
    scored.sort(key=lambda row: (-row[0], row[1]))
    refs = list(explicit)
    if not refs:
        for _score, source_ref, _matched in scored:
            if source_ref not in refs:
                refs.append(source_ref)
            if len(refs) >= limit:
                break
    matched_by_ref = {source_ref: matched for _score, source_ref, matched in scored}
    links = [
        {
            "source_ref": source_ref,
            "title": catalog[source_ref]["title"],
            "source_kind": catalog[source_ref]["kind"],
            "source_status": catalog[source_ref]["status"],
            "relationship": "candidate_context_not_validation",
            "matched_terms": matched_by_ref.get(source_ref, []),
        }
        for source_ref in refs[:limit]
    ]
    return refs[:limit], links


__all__ = [
    "evidence_digest",
    "evidence_links_for_hypothesis",
    "normalize_source_refs",
    "source_catalog",
]
