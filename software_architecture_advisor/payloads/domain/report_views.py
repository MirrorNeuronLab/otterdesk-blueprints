"""Markdown views for the deep architecture evidence bundle."""

from __future__ import annotations

from typing import Any


def render_architecture_report(assessment: dict[str, Any]) -> str:
    evidence = assessment.get("evidence") or {}
    metrics = evidence.get("metrics") or {}
    narrative = assessment.get("report_narrative") or {}
    lines = [
        "# Software Architecture Advisor report",
        "",
        f"**Status:** {assessment['status']}",
        f"**Confidence:** {assessment['confidence']}",
        "",
        "## Executive summary",
        str((narrative.get("executive_summary") or {}).get("text") or assessment["executive_summary"]),
        "",
        "## System reconstruction",
        str((narrative.get("system_reconstruction") or {}).get("text") or "See the deterministic component and dependency evidence below."),
        "",
        "## Cross-cutting analysis",
        str((narrative.get("cross_cutting_analysis") or {}).get("text") or "Cross-cutting runtime behavior remains unverified."),
        "",
        "## Evidence coverage",
    ]
    for name, status in sorted((evidence.get("availability") or {}).items()):
        lines.append(f"- {name.replace('_', ' ').title()}: {status}")
    lines.extend([
        "",
        "## Deterministic architecture evidence",
        f"- Source modules: {metrics.get('module_count', 0)}",
        f"- Indexed symbols: {metrics.get('symbol_count', 0)}",
        f"- Internal dependency edges: {metrics.get('dependency_edge_count', 0)}",
        f"- Static dependency cycles: {metrics.get('cycle_count', 0)}",
        f"- State-store candidates: {metrics.get('state_store_count', 0)}",
        f"- Trust-boundary candidates: {metrics.get('trust_boundary_candidate_count', 0)}",
        f"- Direct static test gaps: {metrics.get('direct_test_gap_count', 0)}",
        "",
        "## Prioritized findings",
        str((narrative.get("finding_rationale") or {}).get("text") or "Findings remain evidence-backed architecture hypotheses."),
        "",
    ])
    for finding in evidence.get("findings") or []:
        lines.extend(_finding_lines(finding))
    lines.extend([
        "## Migration strategy",
        str((narrative.get("migration_strategy") or {}).get("text") or "Implement one reversible, verified improvement at a time."),
        "",
        "## Adversarial review",
        str((assessment.get("adversarial_review") or {}).get("summary") or "No model-authored adversarial summary was available."),
        "",
        "## Review boundary",
        "- This workflow did not execute, modify, test, build, install, upload, or deploy the inspected source.",
        "- Static candidates are not proof of runtime behavior, vulnerabilities, ownership, or production risk.",
        "- Copy-ready implementation prompts are in `improvement_prompts.md` and `codex-prompts/`.",
        "",
    ])
    return "\n".join(lines)


def render_executive_summary(assessment: dict[str, Any]) -> str:
    return "\n".join([
        "# Executive summary",
        "",
        assessment["executive_summary"],
        "",
        f"Overall confidence: **{assessment['confidence']}**",
        f"Recommended action: **{assessment['recommended_action']}**",
        "",
        "The numbered report files separate observed evidence, reconstructed architecture, findings, and migration advice.",
        "",
    ])


def render_repository_map(state: dict[str, Any]) -> str:
    profile = state.get("repository_profile") or {}
    lines = ["# Repository map", "", "## Languages"]
    for language, values in (profile.get("languages") or {}).items():
        lines.append(f"- {language}: {values.get('fraction', 0):.1%} of staged source bytes")
    lines.extend(["", "## Packages and applications"])
    for package in profile.get("packages") or []:
        lines.append(f"- `{package['name']}`: {package['source_file_count']} source files")
    lines.extend(["", "## Entrypoint candidates"])
    lines.extend([f"- `{item['path']}`" for item in profile.get("entrypoints") or []] or ["- None detected statically."])
    lines.extend(["", "## Technology signals"])
    for name in ("frameworks", "data_stores", "queues"):
        lines.append(f"- {name.replace('_', ' ').title()}: {', '.join(profile.get(name) or []) or 'none detected'}")
    lines.extend(["", "## Repository metadata"])
    lines.extend([f"- `{item['path']}` ({item['kind']})" for item in profile.get("metadata_files") or []] or ["- No recognized metadata files were staged."])
    return "\n".join(lines) + "\n"


def render_system_architecture(state: dict[str, Any]) -> str:
    reconstruction = state.get("architecture_reconstruction") or state.get("deterministic_reconstruction") or {}
    lines = [
        "# Reconstructed system architecture",
        "",
        str(reconstruction.get("summary") or "The deterministic reconstruction is recorded below."),
        "",
        "## Components",
    ]
    components = reconstruction.get("components") or []
    lines.extend([
        f"- {item if isinstance(item, str) else item.get('name', item)}"
        + (f" — {item.get('responsibility')}" if isinstance(item, dict) and item.get("responsibility") else "")
        for item in components
    ] or ["- No component list was returned."])
    lines.extend(["", "## Known unknowns"])
    lines.extend([f"- {item}" for item in reconstruction.get("unknowns") or []] or ["- Runtime and production topology remain unverified."])
    return "\n".join(lines) + "\n"


def render_state_model(state: dict[str, Any]) -> str:
    model = state.get("state_model") or {}
    lines = ["# State model", "", "Static candidates; verify actual ownership and durability.", ""]
    for store in model.get("stores") or []:
        lines.extend([
            f"## {store['technology']}",
            f"- Authority: {store.get('authority', 'unknown')}",
            f"- Durability: {store.get('durability', 'unknown')}",
            f"- Writer candidates: {', '.join(f'`{path}`' for path in store.get('writers') or []) or 'none detected'}",
            f"- Reader candidates: {', '.join(f'`{path}`' for path in store.get('readers') or []) or 'none detected'}",
            "",
        ])
    if not model.get("stores"):
        lines.append("No state-store signature was detected in the staged source. This is not proof that the system is stateless.")
    return "\n".join(lines) + "\n"


def render_dependency_analysis(state: dict[str, Any]) -> str:
    metrics = state.get("metrics") or {}
    lines = [
        "# Dependency analysis",
        "",
        f"- Modules: {metrics.get('module_count', 0)}",
        f"- Internal edges: {metrics.get('dependency_edge_count', 0)}",
        f"- Cycles: {metrics.get('cycle_count', 0)}",
        f"- Cross-package edges: {metrics.get('cross_boundary_dependency_count', 0)}",
        "",
        "## Cycles",
    ]
    for cycle in metrics.get("cycles") or []:
        lines.append("- " + " → ".join(f"`{item['path']}`" for item in cycle))
    if not metrics.get("cycles"):
        lines.append("- None resolved statically.")
    lines.extend(["", "## Highest fan-in"])
    lines.extend([f"- `{item['path']}`: {item['count']}" for item in metrics.get("top_fan_in") or []])
    lines.extend(["", "## Highest fan-out"])
    lines.extend([f"- `{item['path']}`: {item['count']}" for item in metrics.get("top_fan_out") or []])
    return "\n".join(lines) + "\n"


def render_hotspots(state: dict[str, Any]) -> str:
    lines = [
        "# Structural hotspots",
        "",
        "Scores fuse static complexity, dependency centrality, direct test links, and Git churn when supplied. They are prioritization proxies, not production-risk measurements.",
        "",
    ]
    for item in state.get("hotspots") or []:
        components = item.get("components") or {}
        lines.append(
            f"- `{item['path']}` — {item['risk_proxy_score']}/10 "
            f"(centrality {components.get('dependency_centrality')}, complexity {components.get('static_complexity')}, "
            f"test-gap {components.get('direct_test_gap')}, churn {components.get('git_churn')})"
        )
    return "\n".join(lines) + "\n"


def render_trust_boundaries(state: dict[str, Any]) -> str:
    model = state.get("trust_model") or {}
    lines = [
        "# Trust-boundary candidates",
        "",
        "These are syntax-pattern candidates. They are not data-flow findings or vulnerability claims.",
        "",
    ]
    for item in model.get("candidate_crossings") or []:
        lines.append(
            f"- `{item['path']}`: ingress={item.get('ingress_signals')}, privileged sinks={item.get('privileged_sink_signals')}"
        )
    if not model.get("candidate_crossings"):
        lines.append("- No co-located ingress/sink candidate was detected.")
    return "\n".join(lines) + "\n"


def render_test_architecture(state: dict[str, Any]) -> str:
    tests = state.get("test_architecture") or {}
    lines = [
        "# Test architecture",
        "",
        f"- Test files detected: {tests.get('test_file_count', 0)}",
        "- Test execution: forbidden by the advisor contract",
        "- Coverage: not measured",
        "",
        "## Direct static test gaps",
    ]
    lines.extend([f"- `{item['path']}` (dependency degree {item['dependency_degree']})" for item in tests.get("direct_test_gaps") or []] or ["- None detected."])
    lines.extend(["", "A missing direct import does not prove missing integration or black-box coverage.", ""])
    return "\n".join(lines)


def render_prioritized_findings(findings: list[dict[str, Any]]) -> str:
    lines = ["# Prioritized architecture findings", ""]
    for finding in findings:
        lines.extend(_finding_lines(finding))
    return "\n".join(lines)


def render_migration_plan(findings: list[dict[str, Any]]) -> str:
    lines = [
        "# Migration plan",
        "",
        "Implement at most one approved finding at a time. Revalidate evidence after each change.",
        "",
    ]
    for finding in findings:
        lines.extend([
            f"## {finding['priority']} — {finding['title']}",
            f"Migration risk: {finding['migration_risk']}",
            "",
        ])
        lines.extend([f"{index}. {item}" for index, item in enumerate(finding.get("migration_sequence") or [], start=1)])
        lines.extend(["", f"Rollback: {finding.get('rollback_considerations')}", ""])
    return "\n".join(lines)


def _finding_lines(finding: dict[str, Any]) -> list[str]:
    lines = [
        f"### {finding['priority']} — {finding['title']}",
        f"Severity: **{finding['severity']}** · Confidence: **{finding['confidence']}** · Score: **{finding['priority_score']}** · Origin: **{finding.get('origin', 'deterministic')}**",
        "",
        f"Observed evidence: {', '.join(finding.get('observed_evidence') or [])}",
        "",
        finding["summary"],
        "",
        f"Interpretation: {finding.get('interpretation')}",
        "",
        f"Model-grounded rationale: {finding.get('llm_rationale') or finding.get('why_it_matters')}",
        "",
        f"Recommended direction: {finding['recommendation']}",
        "",
        "Options:",
    ]
    for option in finding.get("alternative_options") or []:
        recommended = " (recommended)" if option.get("recommended") else ""
        lines.append(f"- {option['option_id']}: {option['title']}{recommended} — {option['tradeoffs']}")
    lines.append("")
    return lines
