"""Validated report proposals and independent evidence-grounding review."""

from .planning import TEXT, STRINGS, object_schema, validate, check_citations

FINDING = object_schema(
    {
        "id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]{1,64}$"},
        "section": {
            "enum": [
                "chronology",
                "findings",
                "subjects",
                "counter_evidence",
                "integrity",
            ]
        },
        "title": dict(TEXT, maxLength=160),
        "assessment": dict(TEXT, maxLength=1200),
        "evidence_ids": dict(STRINGS, minItems=1),
        "limitations": dict(TEXT, maxLength=500),
    }
)
REPORT = object_schema(
    {
        "findings": {"type": "array", "items": FINDING, "maxItems": 1},
        "conclusion_ids": STRINGS,
        "follow_up": STRINGS,
    }
)
REVIEW = object_schema({"accepted_ids": STRINGS, "issues": STRINGS})


def submit_report(data, args, store, investigation_id):
    validate(REPORT, args)
    existing = data.get(
        "report_draft", {"findings": [], "conclusion_ids": [], "follow_up": []}
    )
    merged = {f["id"]: f for f in existing["findings"]}
    merged.update({f["id"]: f for f in args["findings"]})
    if len(merged) > 30:
        raise ValueError("at most 30 accumulated findings")
    ids = list(merged)
    if len(set(ids)) != len(ids) or not set(args["conclusion_ids"]) <= set(ids):
        raise ValueError("duplicate or unknown report finding IDs")
    citations = {i for f in args["findings"] for i in f["evidence_ids"]}
    check_citations(citations, store, investigation_id)
    flagged = data.get("source_review_flags", {})
    if any(
        e.source_id in flagged
        for e in store.evidence_for(investigation_id)
        if e.evidence_id in citations
    ):
        raise ValueError("finding cites material pending human handling review")
    if (
        sum(
            len(e.text.encode("utf-8"))
            for e in store.evidence_for(investigation_id)
            if e.evidence_id in citations
        )
        > 2000
    ):
        raise ValueError(
            "one finding requires at most 2000 UTF-8 bytes of complete evidence; retrieve focused exact spans"
        )
    data["report_draft"] = {
        "findings": list(merged.values()),
        "conclusion_ids": list(
            dict.fromkeys(existing["conclusion_ids"] + args["conclusion_ids"])
        ),
        "follow_up": list(dict.fromkeys(existing["follow_up"] + args["follow_up"]))[
            :40
        ],
    }
    data["pending_review_ids"] = [f["id"] for f in args["findings"]]
    return {"report_draft": args, "next_action": "review_report"}


def review_report(data, args):
    validate(REVIEW, args)
    if "report_draft" not in data:
        raise ValueError("no report draft to review")
    if not set(args["accepted_ids"]) <= set(data.get("pending_review_ids", [])):
        raise ValueError("review accepts unknown findings")
    previous = data.get("report_review", {"accepted_ids": [], "issues": []})
    retained = [
        i
        for i in previous["accepted_ids"]
        if i not in data.get("pending_review_ids", [])
    ]
    data["report_review"] = {
        "accepted_ids": list(dict.fromkeys(retained + args["accepted_ids"])),
        "issues": list(dict.fromkeys(previous["issues"] + args["issues"]))[-40:],
    }
    data.pop("pending_review_ids", None)
    return {"review": args}


def narrative_sections(data, evidence):
    """Render only reviewed findings; prose remains explicitly attributed assessment."""
    draft = data.get("report_draft", {})
    accepted = set(data.get("report_review", {}).get("accepted_ids", []))
    findings = [f for f in draft.get("findings", []) if f["id"] in accepted]
    by_id = {e.evidence_id: e for e in evidence}
    if any(
        by_id[i].source_id in data.get("source_review_flags", {})
        for f in findings
        for i in f["evidence_ids"]
        if i in by_id
    ):
        raise ValueError("reviewed finding cites flagged material")
    if any(not set(f["evidence_ids"]) <= set(by_id) for f in findings):
        raise ValueError("report finding contains unverified evidence")
    lines = [
        "## Principal findings",
        "",
        "Assessments below are model interpretations reviewed against cited source passages; source authenticity and truth are not independently established.",
        "",
    ]
    conclusions = [f for f in findings if f["id"] in draft.get("conclusion_ids", [])]
    for f in conclusions:
        lines += [
            f"- **{f['title']}** — {f['assessment']} See [{f['id']}](#finding-{f['id']})."
        ]
    if not conclusions:
        lines += ["No reviewed principal conclusion was established.", ""]
    for section, title in [
        ("chronology", "Chronology"),
        ("findings", "Investigative findings"),
        ("subjects", "Subject and identity assessments"),
        ("counter_evidence", "Counter-evidence and alternative explanations"),
        ("integrity", "Evidence integrity"),
    ]:
        lines += [f"## {title}", ""]
        selected = [f for f in findings if f["section"] == section]
        if not selected:
            lines += [
                "No reviewed finding recorded for this area; coverage remains incomplete.",
                "",
            ]
        for f in selected:
            lines += [
                f'<a id="finding-{f["id"]}"></a>',
                f"### {f['title']}",
                "",
                f["assessment"],
                "",
            ]
            seen = set()
            for identifier in f["evidence_ids"]:
                e = by_id[identifier]
                key = (e.content_sha256, e.start_offset, e.end_offset)
                if key in seen:
                    continue
                seen.add(key)
                quote = e.text[:800]
                lines += [
                    f"[Evidence {identifier}](evidence_appendix.md#evidence-{identifier}) — `{e.source_id}`",
                    "",
                    *["> " + line for line in quote.splitlines()],
                    "",
                ]
                if len(e.text.encode("utf-8")) > 800:
                    lines += [
                        "Quotation excerpt; the complete retained passage is in the evidence appendix.",
                        "",
                    ]
            lines += ["**Limitations:** " + f["limitations"], ""]
    if data.get("source_review_flags"):
        lines += [
            "### Materials pending human handling review",
            "",
            "Flagged sources were excluded from substantive findings. See the checkpoint for source IDs and recorded reasons.",
            "",
        ]
    lines += [
        "## Report review limitations",
        "",
        *["- " + i for i in data.get("report_review", {}).get("issues", [])],
        "",
    ]
    if "report_review" not in data:
        lines += [
            "Report assessment review did not complete. Proposed narrative findings are withheld.",
            "",
        ]
    lines += [
        "## Prioritized human follow-up",
        "",
        *[f"{i}. {q}" for i, q in enumerate(draft.get("follow_up", []), 1)],
        "",
    ]
    return lines


def evidence_appendix(evidence, derivations=()):
    lines = [
        "# Evidence appendix",
        "",
        "Identical content can have multiple collection locations; copies are not independent corroboration.",
        "",
    ]
    for e in evidence:
        lines += [
            f'<a id="evidence-{e.evidence_id}"></a>',
            f"## {e.evidence_id}",
            "",
            f"Source: `{e.source_id}`; SHA-256: `{e.content_sha256}`; character span: {e.start_offset}:{e.end_offset}.",
            "",
            *["> " + line for line in e.text.splitlines()],
            "",
        ]
    if derivations:
        lines += [
            "## Derived observations",
            "",
            "These are reproducible transformations of cited originals, not verbatim original wording or independent corroboration.",
            "",
        ]
    for item in derivations:
        result = item["result"]
        derived = result["derivation"]
        reference = result["passages"][0]["evidence_id"]
        lines += [
            f"### {derived['method']} (version {derived['version']})",
            "",
            f"Original: [Evidence {reference}](#evidence-{reference}).",
            "",
        ]
        if derived["method"] == "rot13":
            lines += ["> " + line for line in derived["text"].splitlines()] + [""]
        else:
            lines += [
                f"Column `{derived['column']}`; {derived['rows']} rows; exact total `{derived['total']}`. {derived['unit']}.",
                "",
            ]
    return "\n".join(lines)
