"""Complete qualified source inputs for deterministic VC claim extraction."""

from mn_sdk.source_query import source_text_query


def local_source_text(record, terms):
    reference = record.get("context_source")
    if reference is None:
        # Inputs with source query disabled retain their declared preview contract.
        return str(record.get("text_preview") or "")
    sources = source_text_query({"source_context": {"enabled": True}}, principal="vc-company-analysis")
    if sources is None:
        raise ValueError("pinned original source requires the source-query service")
    try:
        # Native source search removes unrelated paragraphs before the bounded
        # deterministic claim extractor runs. Preserve complete returned spans.
        result = sources.query_source(reference, " ".join(terms),
            plan={"intent": "raw", "match_mode": "any", "limit": 128})
        if result["status"] == "not_found_in_searched_scope":
            return ""
        if result["status"] != "ready" or result.get("unresolved"):
            raise ValueError("original-source claim query could not provide complete selected spans")
        return "\n".join(item["content"] for bundle in result["bundles"] for item in bundle["items"])
    finally:
        sources.close()
