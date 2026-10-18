"""Conservative source handling flags, never a determination of legal privilege."""
import re

MARKERS = (
    "attorney client privileged", "attorney client communication",
    "privileged and confidential", "legal professional privilege",
    "attorney work product", "seeking legal representation",
    "seeking legal advice", "request for legal representation",
)
REASON = "Potential privileged material; human handling review required."


def potential_privilege(text):
    normalized = re.sub(r"[-\u2010-\u2015]", " ", (text or "").casefold())
    normalized = " ".join(normalized.split())
    return any(marker in normalized for marker in MARKERS)


def review_flags(documents, exclusions=()):
    documents = tuple(documents)
    known = {d.source_id for d in documents} | {d.container_source_id for d in documents if d.container_source_id}
    if len({r["source_id"] for r in exclusions}) != len(exclusions):
        raise ValueError("Reviewed exclusions must name each source once")
    if any(r["source_id"] not in known for r in exclusions):
        raise ValueError("Reviewed exclusion names a source outside the frozen matter")
    decisions = {r["source_id"]: r for r in exclusions}
    flags = {d.source_id: REASON for d in documents if potential_privilege(d.text)}
    for document in documents:
        row = decisions.get(document.source_id) or decisions.get(document.container_source_id)
        if row:
            flags[document.source_id] = f"Excluded by {row['reviewer']} at {row['reviewed_at']}: {row['reason']}"
    return flags


def cleared_observation(value, flagged):
    """Omit graph rows bound to excluded source IDs before model/report projection."""
    if isinstance(value, dict):
        if any(k.endswith("source_id") and isinstance(v, str) and v in flagged for k, v in value.items()):
            return None
        return {k: cleared_observation(v, flagged) for k, v in value.items()}
    if isinstance(value, list):
        return [clean for v in value if (clean := cleared_observation(v, flagged)) is not None]
    return value
