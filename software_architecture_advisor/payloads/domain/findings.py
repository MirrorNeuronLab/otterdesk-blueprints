"""Deterministic architecture hypotheses, options, and priority scoring."""

from __future__ import annotations

from typing import Any


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_findings(
    state: dict[str, Any], settings: dict[str, Any]
) -> list[dict[str, Any]]:
    metrics = state.get("metrics") or {}
    facts = ((state.get("architecture_facts") or {}).get("facts") or [])
    tests = state.get("test_architecture") or {}
    history = state.get("history_evidence") or {}
    profile = state.get("repository_profile") or {}
    findings: list[dict[str, Any]] = []

    for index, cycle in enumerate(metrics.get("cycles") or [], start=1):
        paths = [item["path"] for item in cycle]
        findings.append(_finding(
            finding_id=f"dependency-cycle-{index}",
            title="Break a static dependency cycle",
            category="dependency_architecture",
            desired_severity="high",
            summary="A statically resolved import cycle increases change-propagation risk and can make module initialization order brittle.",
            interpretation="The modules form a strongly connected dependency component; ownership direction is not explicit in the static graph.",
            why_it_matters="A change or initialization concern can propagate around the cycle, complicating isolated testing and future replacement.",
            paths=paths,
            metrics={"cycle_count": metrics.get("cycle_count", 0), "cycle_modules": [item["module"] for item in cycle]},
            supporting_facts=_matching_facts(facts, {"dependency_cycle", "direct_test_gap", "git_churn", "structural_hotspot"}, paths),
            recommendation="Choose one ownership direction and introduce the smallest explicit seam that removes the reverse dependency.",
            options=[
                _option("A", "Dependency inversion", "Introduce a narrow interface owned by the higher-level policy module.", "Small-to-medium change; best when one side is a replaceable provider.", True),
                _option("B", "Extract stable collaboration data", "Move only shared contracts or immutable data into a lower-level module.", "Small change when the cycle is caused by shared types; avoid a miscellaneous common module."),
                _option("C", "Event boundary", "Publish an explicit domain event instead of calling back into the originating module.", "Higher operational and testing cost; useful only when asynchronous decoupling is already natural."),
            ],
            counter_checks=_counter_checks(paths, tests, history, profile),
            migration_risk="medium",
            migration_sequence=[
                "Characterize existing behavior at the cycle boundary with focused tests.",
                "Select and document the intended ownership direction.",
                "Introduce the seam and move one dependency at a time.",
                "Verify the static cycle is removed and behavior remains stable.",
            ],
            test_strategy=[
                "Add characterization tests around both cited modules.",
                "Add an architecture/import-boundary regression test when the language supports it.",
                "Run the relevant existing unit and integration suites.",
            ],
            rollback="Keep the seam behavior-preserving so the dependency redirection can be reverted without data migration.",
        ))

    fan_in = {item["module"]: item for item in metrics.get("top_fan_in") or []}
    fan_out = {item["module"]: item for item in metrics.get("top_fan_out") or []}
    gravity_threshold = int(settings.get("architecture_gravity_min_degree", 4))
    gravity_modules = sorted(
        module for module in set(fan_in) & set(fan_out)
        if int(fan_in[module].get("count", 0)) >= gravity_threshold
        and int(fan_out[module].get("count", 0)) >= gravity_threshold
    )
    for index, module in enumerate(gravity_modules[:5], start=1):
        path = fan_in[module]["path"]
        findings.append(_finding(
            finding_id=f"architecture-gravity-{index}",
            title="Reduce architectural gravity around a highly connected module",
            category="change_risk",
            desired_severity="high",
            summary=f"{path} has both high fan-in ({fan_in[module]['count']}) and high fan-out ({fan_out[module]['count']}).",
            interpretation="The module is a static coordination hub and may concentrate unrelated change paths.",
            why_it_matters="Highly connected modules can amplify change risk and make otherwise independent components difficult to evolve.",
            paths=[path],
            metrics={"fan_in": fan_in[module]["count"], "fan_out": fan_out[module]["count"]},
            supporting_facts=_matching_facts(facts, {"structural_hotspot", "direct_test_gap", "git_churn"}, [path]),
            recommendation="Identify the module's stable policy responsibility, then move peripheral coordination behind explicit ports without creating a generic facade.",
            options=[
                _option("A", "Narrow the public surface", "Keep the module but reduce exported responsibilities and dependency reach.", "Lowest migration cost when ownership is cohesive.", True),
                _option("B", "Extract one cohesive responsibility", "Move a well-tested responsibility and its dependencies behind an explicit contract.", "Useful when change history and tests support a real seam."),
            ],
            counter_checks=_counter_checks([path], tests, history, profile),
            migration_risk="medium",
            migration_sequence=["Map callers and callees.", "Name the stable responsibility.", "Add contract tests.", "Move one responsibility and validate dependency metrics."],
            test_strategy=["Protect the current public contract.", "Exercise representative callers and provider failures."],
            rollback="Preserve the original entrypoint until all callers use the new seam, then remove it separately.",
        ))

    for index, candidate in enumerate((state.get("state_model") or {}).get("ownership_candidates") or [], start=1):
        paths = list(candidate.get("writers") or [])
        findings.append(_finding(
            finding_id=f"state-ownership-{index}",
            title="Clarify state ownership across multiple writer candidates",
            category="state_ownership",
            desired_severity="high",
            summary=f"Static patterns identify multiple writer candidates for {candidate.get('state_id', 'a state store')}.",
            interpretation="The durable authority, consistency model, and retry behavior are not explicit in the staged evidence.",
            why_it_matters="Multiple writers can create divergent state after partial failure unless ownership and reconciliation are explicit.",
            paths=paths,
            metrics={"writer_candidate_count": len(paths)},
            supporting_facts=_matching_facts(facts, {"ambiguous_state_ownership_candidate", "state_store_reference", "git_churn", "direct_test_gap"}, paths),
            recommendation="Document one authority and its consistency guarantees before changing code; then centralize or reconcile writes through the smallest enforceable boundary.",
            options=[
                _option("A", "Single writer boundary", "Route mutations through one owner while retaining read replicas or caches.", "Strongest invariant when operationally practical.", True),
                _option("B", "Versioned reconciliation", "Keep distributed writers but add versioning, idempotency, and an explicit reconciliation path.", "Higher operational complexity; justified when independent writers are required."),
            ],
            counter_checks=_counter_checks(paths, tests, history, profile),
            migration_risk="high",
            migration_sequence=["Confirm actual readers and writers.", "Choose the authority.", "Add consistency and retry tests.", "Migrate one write path at a time.", "Add reconciliation observability."],
            test_strategy=["Test partial failure between each state transition.", "Test duplicate delivery and retries.", "Verify stale data recovery."],
            rollback="Use a reversible routing switch or dual-read validation period; avoid irreversible data migration in the first change.",
        ))

    for index, crossing in enumerate((state.get("trust_model") or {}).get("candidate_crossings") or [], start=1):
        path = crossing["path"]
        findings.append(_finding(
            finding_id=f"trust-boundary-{index}",
            title="Verify an ingress-to-privileged-operation boundary",
            category="trust_boundary",
            desired_severity="medium",
            summary=f"{path} contains both ingress and privileged-operation patterns.",
            interpretation="This is a candidate trust-boundary crossing; static co-location does not establish data flow or a vulnerability.",
            why_it_matters="If user-controlled data reaches a privileged capability, validation and capability isolation belong at an explicit boundary.",
            paths=[path],
            metrics={"ingress_signals": crossing.get("ingress_signals") or [], "privileged_sink_signals": crossing.get("privileged_sink_signals") or []},
            supporting_facts=_matching_facts(facts, {"trust_boundary_crossing_candidate", "endpoint_candidate", "direct_test_gap"}, [path]),
            recommendation="Trace the concrete data flow and authorization path first; only then strengthen validation or isolate the privileged capability.",
            options=[
                _option("A", "Capability boundary", "Move privileged work behind a narrow validated interface with least privilege.", "Preferred if a real user-controlled flow is confirmed.", True),
                _option("B", "Documented false positive", "Record why the values cannot interact and add a regression test for that invariant.", "Appropriate when data-flow inspection disproves the hypothesis."),
            ],
            counter_checks=_counter_checks([path], tests, history, profile),
            migration_risk="high",
            migration_sequence=["Trace source-to-sink data flow.", "Confirm authentication and authorization.", "Add a failing abuse-case test.", "Introduce the least-privilege seam if required."],
            test_strategy=["Exercise unauthorized, malformed, and replayed input.", "Verify the privileged operation receives only validated typed data."],
            rollback="Keep the existing path available only behind a controlled rollback mechanism if production compatibility requires it.",
        ))

    large_paths = {item["path"] for item in metrics.get("large_modules") or []}
    hotspot_threshold = float(settings.get("hotspot_risk_threshold", 6.0))
    for index, hotspot in enumerate(metrics.get("structural_hotspots") or [], start=1):
        path = hotspot["path"]
        if float(hotspot.get("risk_proxy_score", 0)) < hotspot_threshold:
            continue
        if path in large_paths or any(path in item.get("evidence", {}).get("paths", []) for item in findings):
            continue
        findings.append(_finding(
            finding_id=f"structural-hotspot-{index}",
            title="Investigate a fused structural change-risk hotspot",
            category="change_risk",
            desired_severity="medium",
            summary=f"{path} has a structural risk proxy score of {hotspot['risk_proxy_score']} from dependency, complexity, test-link, and available history signals.",
            interpretation="The file is a candidate for focused architecture discovery, not an automatic refactoring target.",
            why_it_matters="Concentrated structural signals identify a useful place to validate developer friction and production criticality.",
            paths=[path],
            metrics=hotspot,
            supporting_facts=_matching_facts(facts, {"structural_hotspot", "direct_test_gap", "git_churn", "large_module"}, [path]),
            recommendation="Validate responsibilities, change history, and test protection, then improve only the highest-leverage confirmed seam.",
            options=[
                _option("A", "Harden in place", "Add characterization and boundary tests before restructuring.", "Best when the module is cohesive or stable.", True),
                _option("B", "Extract one responsibility", "Move one cohesive behavior behind a contract.", "Use only when history and ownership support the seam."),
            ],
            counter_checks=_counter_checks([path], tests, history, profile),
            migration_risk="low-to-medium",
            migration_sequence=["Confirm the hotspot with maintainers and history.", "Add characterization tests.", "Make one bounded change.", "Recalculate structural evidence."],
            test_strategy=["Add tests for the selected responsibility and its callers.", "Preserve external behavior."],
            rollback="Keep the change behavior-preserving and isolated to one seam.",
        ))

    if not findings:
        findings.append(_finding(
            finding_id="guided-architecture-discovery",
            title="Perform evidence-led architecture discovery before refactoring",
            category="discovery",
            desired_severity="low",
            summary="The bounded static scan did not produce a sufficiently triangulated structural refactoring target.",
            interpretation="More runtime, history, ownership, or test evidence is needed before recommending an architectural change.",
            why_it_matters="Avoiding an unsupported refactor is a valid architecture outcome.",
            paths=[],
            metrics={"module_count": metrics.get("module_count", 0), "fact_count": len(facts)},
            supporting_facts=_matching_facts(facts, {"language_distribution", "repository_descriptor", "structural_hotspot"}, [])[:5],
            recommendation="Collect targeted runtime flows, Git hotspots, state ownership, and boundary tests before proposing a structural change.",
            options=[
                _option("A", "Evidence collection", "Stage history, runtime, or test evidence and rerun the advisor.", "Lowest-risk next step.", True),
                _option("B", "Maintainer workshop", "Validate components, state authority, and failure-sensitive flows with subsystem owners.", "Useful when operational knowledge is not encoded in the repository."),
            ],
            counter_checks=_counter_checks([], tests, history, profile),
            migration_risk="none",
            migration_sequence=["Collect missing evidence.", "Rerun analysis.", "Approve one bounded implementation prompt."],
            test_strategy=["No code change is recommended yet."],
            rollback="Not applicable.",
        ))

    return sorted(
        findings,
        key=lambda item: (
            _SEVERITY_RANK[item["severity"]], -item["priority_score"], item["finding_id"]
        ),
    )[:12]


def build_llm_grounded_finding(
    state: dict[str, Any], candidate: dict[str, Any], index: int
) -> dict[str, Any]:
    """Convert one validated model candidate into the authoritative finding shape."""
    facts_by_id = {
        str(item.get("fact_id")): item
        for item in ((state.get("architecture_facts") or {}).get("facts") or [])
        if item.get("fact_id")
    }
    cited = [facts_by_id[item] for item in candidate.get("fact_ids") or [] if item in facts_by_id]
    finding = _finding(
        finding_id=str(candidate.get("finding_id") or f"llm-grounded-{index}"),
        title=str(candidate["title"]),
        category=str(candidate.get("category") or "architecture_design"),
        desired_severity=str(candidate.get("severity") or "medium").lower(),
        summary=str(candidate["summary"]),
        interpretation=str(candidate["interpretation"]),
        why_it_matters=str(candidate["why_it_matters"]),
        paths=list(candidate.get("paths") or []),
        metrics={},
        supporting_facts=cited,
        recommendation=str(candidate["recommendation"]),
        options=list(candidate["alternative_options"]),
        counter_checks=list(candidate["counter_evidence_considered"]),
        migration_risk=str(candidate.get("migration_risk") or "medium"),
        migration_sequence=list(candidate["migration_sequence"]),
        test_strategy=list(candidate["test_strategy"]),
        rollback=str(candidate["rollback_considerations"]),
        origin="llm_grounded",
    )
    finding["stop_conditions"] = list(candidate.get("stop_conditions") or [])
    return finding


def _finding(
    *, finding_id: str, title: str, category: str, desired_severity: str,
    summary: str, interpretation: str, why_it_matters: str, paths: list[str],
    metrics: dict[str, Any], supporting_facts: list[dict[str, Any]],
    recommendation: str, options: list[dict[str, Any]],
    counter_checks: list[dict[str, Any]], migration_risk: str,
    migration_sequence: list[str], test_strategy: list[str], rollback: str,
    origin: str = "deterministic",
) -> dict[str, Any]:
    signal_types = sorted({
        item.get("evidence_type") for item in supporting_facts
        if item.get("evidence_type")
    })
    severity = desired_severity
    if desired_severity in {"critical", "high"} and len(signal_types) < 2:
        severity = "medium"
    confidence = (
        "high" if len(signal_types) >= 3
        else "medium" if len(signal_types) >= 2
        else "low"
    )
    if any(item.get("status") == "potential_counter_evidence_found" for item in counter_checks):
        confidence = {"high": "medium", "medium": "low", "low": "low"}[confidence]
    risk = {"critical": 10, "high": 8, "medium": 5, "low": 2}[severity]
    leverage = min(10, 4 + len(set(paths)) + len(signal_types))
    evidence_score = min(10, 2 + 2 * len(signal_types))
    migration_cost = {
        "none": 1, "low": 2, "low-to-medium": 4, "medium": 5, "high": 8,
    }.get(migration_risk, 5)
    priority_score = round(
        10 * (
            risk * 0.4 + leverage * 0.25 + evidence_score * 0.25
            + (10 - migration_cost) * 0.1
        ),
        1,
    )
    priority = (
        "P0" if priority_score >= 80 else "P1" if priority_score >= 65
        else "P2" if priority_score >= 45 else "P3"
    )
    fact_ids = [item["fact_id"] for item in supporting_facts]
    return {
        "origin": origin,
        "finding_id": finding_id,
        "title": title,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "priority": priority,
        "priority_score": priority_score,
        "summary": summary,
        "observed_evidence": fact_ids,
        "interpretation": interpretation,
        "why_it_matters": why_it_matters,
        "evidence": {
            "fact_ids": fact_ids,
            "signal_types": signal_types,
            "paths": sorted(set(paths)),
            "metrics": metrics,
        },
        "counter_evidence_considered": counter_checks,
        "recommendation": recommendation,
        "recommended_option_id": next(
            (item["option_id"] for item in options if item.get("recommended")),
            options[0]["option_id"],
        ),
        "alternative_options": options,
        "migration_risk": migration_risk,
        "migration_sequence": migration_sequence,
        "test_strategy": test_strategy,
        "rollback_considerations": rollback,
        "expected_benefit": why_it_matters,
        "limitations": [
            "The finding is an architecture hypothesis derived from bounded static evidence.",
            "Runtime behavior, production criticality, ownership, and migration cost require human verification.",
        ],
    }


def _matching_facts(
    facts: list[dict[str, Any]], fact_types: set[str], paths: list[str]
) -> list[dict[str, Any]]:
    wanted_paths = set(paths)
    return [
        item for item in facts
        if item.get("fact_type") in fact_types
        and (not wanted_paths or wanted_paths.intersection(item.get("paths") or []))
    ][:20]


def _counter_checks(
    paths: list[str], tests: dict[str, Any], history: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    gap_paths = {item.get("path") for item in tests.get("direct_test_gaps") or []}
    observations = (profile.get("documentation_observations") or [])[:10]
    test_status = (
        "no_direct_static_test_import" if any(path in gap_paths for path in paths)
        else "direct_test_gap_not_observed"
    )
    return [
        {"check": "direct static test protection", "status": test_status, "limitation": "Indirect and black-box coverage remain unknown."},
        {"check": "Git churn and co-change", "status": "available" if history.get("available") else "not_supplied", "limitation": history.get("reason")},
        {
            "check": "architecture documentation",
            "status": "potential_counter_evidence_found" if observations else "available" if profile.get("architecture_documents") else "not_found_in_staged_metadata",
            "paths": (profile.get("architecture_documents") or [])[:10],
            "observations": observations,
        },
        {"check": "runtime traces", "status": "not_supplied", "limitation": "Static evidence cannot confirm exercised production paths."},
    ]


def _option(
    option_id: str, title: str, direction: str, tradeoffs: str,
    recommended: bool = False,
) -> dict[str, Any]:
    return {
        "option_id": option_id,
        "title": title,
        "direction": direction,
        "tradeoffs": tradeoffs,
        "recommended": recommended,
    }
