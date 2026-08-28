"""Copy-ready, implementation-safe prompts derived only from recorded evidence."""

from __future__ import annotations

from typing import Any

from .model_analysis import known_fact_ids, run_model_stage, string_list, structured_packet, text, validate_references
from .state import read_state, write_state


def author_prompts(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = read_state(ctx)
    findings = state.get("findings") or []
    fallback = {
        "summary": "Implementation prompts preserve the reviewed architecture intent while requiring current-checkout verification and reversible, tested changes.",
        "prompts": [
            {
                "finding_id": finding["finding_id"],
                "objective": finding["recommendation"],
                "architecture_intent": finding.get("interpretation") or finding["summary"],
                "option_guidance": [f"Evaluate {item['option_id']}: {item['title']} — {item['tradeoffs']}" for item in finding.get("alternative_options") or []],
                "implementation_steps": list(finding.get("migration_sequence") or []),
                "tests": list(finding.get("test_strategy") or []),
                "rollback": finding.get("rollback_considerations") or "Keep the change reversible.",
                "stop_conditions": list(finding.get("stop_conditions") or [
                    "Stop if cited evidence is stale or contradicted by the current checkout.",
                    "Stop if behavior preservation cannot be verified with focused tests.",
                    "Stop and ask for approval before a data migration, public contract change, deployment, or new runtime dependency.",
                ]),
                "fact_ids": list((finding.get("evidence") or {}).get("fact_ids") or []),
            }
            for finding in findings
        ],
    }
    authored = run_model_stage(
        ctx,
        state,
        stage="prompt_authoring",
        task="Generate copy-ready implementation guidance with evidence, options, tests, rollback, and stop conditions.",
        context=structured_packet(state, surviving_findings=findings, adversarial_review=state.get("adversarial_review") or {}),
        fallback=fallback,
        validator=lambda value: _validate_authored_prompts(value, findings=findings, fact_ids=known_fact_ids(state)),
        llm_client=llm_client,
    )
    guidance = {item["finding_id"]: item for item in authored["prompts"]}
    prompts = [_prompt_for(finding, index, guidance[finding["finding_id"]]) for index, finding in enumerate(findings, start=1)]
    state["prompt_authoring"] = authored
    state["prompt_pack"] = prompts
    write_state(ctx, state)
    return {"prompt_count": len(prompts), "prompt_ids": [item["prompt_id"] for item in prompts]}


def _prompt_for(
    finding: dict[str, Any], index: int, guidance: dict[str, Any]
) -> dict[str, Any]:
    paths = finding.get("evidence", {}).get("paths") or []
    cited = ", ".join(f"`{path}`" for path in paths) or "the architecture assessment evidence bundle"
    fact_ids = ", ".join(finding.get("evidence", {}).get("fact_ids") or []) or "none"
    options = finding.get("alternative_options") or []
    recommended_option = finding.get("recommended_option_id") or ""
    body = "\n".join([
        f"# Improvement {index}: {finding['title']}",
        "",
        "You are an implementation agent working in an existing repository. First inspect the cited paths and the surrounding tests; do not assume this assessment is complete.",
        "",
        "## Objective",
        guidance["objective"],
        "",
        "## Architecture intent",
        guidance["architecture_intent"],
        "",
        "## Evidence to validate",
        f"- Finding: {finding['summary']}",
        f"- Priority: {finding.get('priority', 'unranked')} (score {finding.get('priority_score', 'unknown')})",
        f"- Confidence: {finding.get('confidence', 'unknown')}",
        f"- Fact IDs: {fact_ids}",
        f"- Cited paths: {cited}",
        f"- Static metrics: {finding.get('evidence', {}).get('metrics', {})}",
        "",
        "## Counter-evidence to check",
        *[_counter_check_line(item) for item in finding.get("counter_evidence_considered") or []],
        "",
        "## Options to evaluate",
        *[f"- {item}" for item in guidance["option_guidance"]],
        "",
        "## Likely files",
        *([f"- `{path}`" for path in paths] or ["- Discover the relevant files from the cited fact records before editing."]),
        "",
        "## Required behavior",
        "- Preserve externally observed behavior unless the approved option explicitly changes a documented contract.",
        "- Keep state ownership, failure behavior, dependency direction, and public interfaces explicit.",
        "",
        "## Required approach",
        "- Confirm the evidence in the current checkout before editing; stop and explain if it is stale or contradicted.",
        f"- Evaluate all listed options; use option {recommended_option or 'A'} only if repository evidence supports its tradeoffs.",
        "- Make the smallest cohesive change that improves the named boundary without changing externally observed behavior unless you explicitly document a contract change.",
        "- Keep ownership, dependencies, and public interfaces explicit. Do not introduce a broad compatibility layer or a generic abstraction merely to hide the problem.",
        "",
        "## Migration sequence",
        *[f"{position}. {item}" for position, item in enumerate(guidance["implementation_steps"], start=1)],
        "",
        "## Tests",
        *[f"- {item}" for item in guidance["tests"]],
        "- Run the relevant existing test suite and report exact commands and results.",
        "",
        "## Implementation constraints",
        f"- Treat migration risk as {finding.get('migration_risk', 'unknown')}; split the work if safe verification cannot fit one change.",
        "- Cite the concrete code and tests that confirm or contradict each architecture assumption.",
        "- Avoid new runtime dependencies unless the selected option clearly requires one and the user approves it.",
        "",
        "## Non-goals and safeguards",
        "- Do not modify unrelated code, deploy, change credentials, or weaken validation/security controls.",
        "- Do not delete a cycle, split a module, or change an interface mechanically: preserve behavior and explain the ownership decision.",
        "- Treat runtime behavior, performance, and production ownership as unknown until verified from code, tests, and maintainers.",
        "",
        "## Rollback considerations",
        f"- {guidance['rollback']}",
        "",
        "## Stop conditions",
        *[f"- {item}" for item in guidance["stop_conditions"]],
        "",
        "## Acceptance criteria",
        "- The cited structural concern is measurably improved or the evidence explains why no safe change is justified.",
        "- New or updated tests pass along with the relevant existing suite.",
        "- The selected option and rejected alternatives are documented with repository-specific evidence.",
        "- The final response states changed files, the dependency/ownership result, verification run, and any remaining risk.",
    ])
    return {
        "prompt_id": f"architecture-improvement-{index}",
        "finding_id": finding["finding_id"],
        "title": finding["title"],
        "priority": finding.get("priority"),
        "severity": finding["severity"],
        "confidence": finding.get("confidence"),
        "fact_ids": finding.get("evidence", {}).get("fact_ids") or [],
        "origin": finding.get("origin") or "deterministic",
        "body": body,
    }


def _validate_authored_prompts(
    value: dict[str, Any], *, findings: list[dict[str, Any]], fact_ids: set[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("prompts"), list):
        return None
    expected = {item["finding_id"] for item in findings}
    seen = set()
    prompts = []
    for item in value["prompts"]:
        if not isinstance(item, dict):
            return None
        finding_id = str(item.get("finding_id") or "")
        cited = validate_references(item.get("fact_ids"), fact_ids, allow_empty=False)
        option_guidance = string_list(item.get("option_guidance"), maximum_items=10)
        steps = string_list(item.get("implementation_steps"), maximum_items=16)
        tests = string_list(item.get("tests"), maximum_items=16)
        stops = string_list(item.get("stop_conditions"), maximum_items=12)
        if finding_id not in expected or finding_id in seen or cited is None or option_guidance is None or len(option_guidance) < 2 or not steps or not tests or not stops:
            return None
        objective = text(item.get("objective"), maximum=2400)
        intent = text(item.get("architecture_intent"), maximum=2400)
        rollback = text(item.get("rollback"), maximum=1600)
        if not objective or not intent or not rollback:
            return None
        seen.add(finding_id)
        prompts.append({
            "finding_id": finding_id,
            "objective": objective,
            "architecture_intent": intent,
            "option_guidance": option_guidance,
            "implementation_steps": steps,
            "tests": tests,
            "rollback": rollback,
            "stop_conditions": stops,
            "fact_ids": cited,
        })
    if seen != expected:
        return None
    summary = text(value.get("summary"), maximum=3600)
    return {"summary": summary, "prompts": prompts} if summary else None


def _counter_check_line(item: dict[str, Any]) -> str:
    line = f"- {item.get('check')}: {item.get('status')}"
    if item.get("limitation"):
        line += f" — {item['limitation']}"
    observations = item.get("observations") or []
    if observations:
        rendered = "; ".join(
            f"{observation.get('path')}:{observation.get('line')} markers={','.join(observation.get('matched_markers') or [])}"
            for observation in observations[:3]
        )
        line += f" — Relevant staged documentation: {rendered}"
    return line


def render_prompt_markdown(prompt_pack: list[dict[str, Any]]) -> str:
    intro = ["# Copy-ready architecture improvement prompts", "", "Each prompt is advisory output from a read-only analysis. Validate it against the current checkout before making changes.", ""]
    return "\n\n".join([*intro, *(item["body"] for item in prompt_pack)]) + "\n"
