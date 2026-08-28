"""LLM-authored analytical narrative draft; no artifact publication occurs here."""

from __future__ import annotations

import re
from typing import Any

from .model_analysis import known_fact_ids, run_model_stage, structured_packet, text, validate_references
from .state import read_state, write_state


SECTION_NAMES = (
    "executive_summary",
    "system_reconstruction",
    "cross_cutting_analysis",
    "finding_rationale",
    "migration_strategy",
)
_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")


def draft_architecture_report(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = read_state(ctx)
    findings = state.get("findings") or []
    cited = list(dict.fromkeys(
        fact_id
        for finding in findings
        for fact_id in ((finding.get("evidence") or {}).get("fact_ids") or [])
    ))
    fallback = {
        "sections": {
            "executive_summary": {
                "text": "The review identified evidence-backed architecture hypotheses that should be validated against the current checkout before one reversible improvement is selected.",
                "fact_ids": cited[:20],
            },
            "system_reconstruction": {
                "text": "The reconstructed system is organized around the components and dependency directions recorded in the static evidence. Runtime composition remains unverified.",
                "fact_ids": cited[:20],
            },
            "cross_cutting_analysis": {
                "text": "State ownership, trust boundaries, deployment interactions, and test seams remain bounded interpretations of static patterns rather than observed production behavior.",
                "fact_ids": cited[:20],
            },
            "finding_rationale": {
                "text": "The surviving findings balance structural evidence, counter-evidence, alternatives, and missing runtime context; none should be treated as an automatic refactoring instruction.",
                "fact_ids": cited[:30],
            },
            "migration_strategy": {
                "text": "Choose one approved finding, confirm its evidence, characterize current behavior, implement the smallest cohesive seam, verify it, and retain a practical rollback path.",
                "fact_ids": cited[:20],
            },
        },
        "coverage": list(SECTION_NAMES),
    }
    draft = run_model_stage(
        ctx,
        state,
        stage="report_synthesis",
        task="Write the analytical narrative sections; deterministic renderers own exact facts, metrics, tables, and safety notices.",
        context=structured_packet(
            state,
            investigation_plan=state.get("investigation_plan") or {},
            architecture_reconstruction=state.get("architecture_reconstruction") or {},
            cross_cutting_analysis=state.get("cross_cutting_analysis") or {},
            findings=findings,
            adversarial_review=state.get("adversarial_review") or {},
            prompt_metadata=[{key: item.get(key) for key in ("prompt_id", "finding_id", "title", "fact_ids")} for item in state.get("prompt_pack") or []],
        ),
        fallback=fallback,
        validator=lambda value: _validate_report_draft(value, fact_ids=known_fact_ids(state)),
        llm_client=llm_client,
    )
    state["report_draft"] = draft
    write_state(ctx, state)
    return {"section_count": len(draft["sections"]), "coverage": draft["coverage"]}


def _validate_report_draft(
    value: dict[str, Any], *, fact_ids: set[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("sections"), dict):
        return None
    if set(value["sections"]) != set(SECTION_NAMES):
        return None
    sections = {}
    for name in SECTION_NAMES:
        item = value["sections"].get(name)
        if not isinstance(item, dict):
            return None
        prose = text(item.get("text"), maximum=7000)
        cited = validate_references(item.get("fact_ids"), fact_ids, allow_empty=False)
        # Exact metrics and tables are deterministic; model prose must not emit
        # new numeric claims. Fact IDs are citations and are ignored here.
        numeric_probe = re.sub(r"\bF\d+\b", "", prose)
        if not prose or cited is None or _NUMBER.search(numeric_probe):
            return None
        sections[name] = {"text": prose, "fact_ids": cited}
    coverage = value.get("coverage")
    if not isinstance(coverage, list) or set(map(str, coverage)) != set(SECTION_NAMES):
        return None
    return {"sections": sections, "coverage": list(SECTION_NAMES)}


__all__ = ["SECTION_NAMES", "draft_architecture_report"]
