"""Goal → falsifiable hypotheses → graph + passages → cited review draft."""
from __future__ import annotations
import json
from pathlib import Path
import re
import time
from .events import emit, current_run, event_context, intent_created

from .graph import QuerySession
from .model import JsonModel
from .knowledge import KnowledgeBase, GUIDANCE, with_guidance, evidence_room
from .prompts import render_prompts, anchor
from .catalog import LayerUnavailable


FAMILIES = {
    "coupling": ["inbound_count", "dependencies", "cycles"],
    "ownership": ["tables", "shared_tables", "dependencies"],
    "layering": ["layers", "dependencies", "inbound_count"],
    "history": ["changes", "cochange", "dependencies"],
    "resilience": ["calls", "control_flow", "state"],
    "data_flow": ["data_flow", "state", "security"],
    "verification": ["tests", "test_call_links", "call_state"],
    "abstraction": ["types", "references", "dependencies"],
    "responsibility": ["responsibilities", "calls", "state"],
    "intent_verification": ["intent", "state", "intent_violations"],
    "runtime": ["deployment", "api", "events"],
    "schema_evolution": ["schema", "state", "shared_tables"],
    "workflow": ["workflow_states", "calls", "events"],
    "incident_analysis": ["incident_links", "changes", "cochange"],
    "team_ownership": ["ownership", "dependencies", "changes"],
    "configuration": ["configuration", "api", "deployment"],
    "drift": ["layers", "changes", "dependencies"],
    "duplication": ["shared_tables", "dependencies", "inbound_count"],
}

PLAN = """Generate falsifiable architecture hypotheses relevant to goal and candidate modules.
Return {"hypotheses":[{"module":"exact name", "family":"one allowed family",
"statement":"testable hypothesis, not a factual assertion", "semantic_query":"support search",
"counter_query":"search for evidence that would disprove it"}]}.
State hypotheses about current implementation that source/graph evidence can falsify, not
unmeasured predictions that a proposed refactor will improve performance or lower risk.
semantic_query and counter_query must be short natural-language search phrases, NEVER SQL or RGQL.
Do not invent tables, layers or schemas. Example semantic_query: "retry repeats external side effects".
Use at most max_hypotheses, different module/family pairs. Search actual behavior and cohesion,
transaction boundaries, intentional orchestration, documented exceptions. No extra fields."""

ASSESS = """Assess the hypothesis from this packet only, using the enforced JSON schema.
verdict: supported, contradicted or inconclusive. interpretation: concise text plus evidence_ids.
counter_evidence: observed disconfirming signals with citations; [] if none established.
recommendation and next_action: concrete, reversible and conditional on decisive unknowns.
acceptance_test: measurable target or failure-injection test. rollback: reverse the proposed first step.
tradeoffs: possible costs; alternatives: another option and when preferred; missing_evidence: decisive gaps.
Use only visible citation IDs. Do not infer absence from top-k results or cohesion from similarity.
A layer violation needs an explicit allowed-dependency rule. A new wrapper does not establish
idempotency; a local transaction cannot undo an external charge. For inconclusive evidence,
resolve the uncertainty or add characterization tests BEFORE prescribing a split. Describe visible
code accurately; distinguish it from missing runtime guarantees. Keep each field to one or two
sentences and each list to at most two items. Do not restate graph counts or dependency directions
in prose; the report already renders them directly from the query results."""


PLAN += GUIDANCE
ASSESS += GUIDANCE


def bounded_text(value, field, maximum=1200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


def validate_plan(value, candidates, count):
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or not 1 <= len(hypotheses) <= count:
        raise ValueError("Invalid hypothesis count")
    seen = set()
    for h in hypotheses:
        if not isinstance(h, dict) or h.get("module") not in candidates or h.get("family") not in FAMILIES:
            raise ValueError("Model selected an unknown module or tool family")
        pair = h["module"], h["family"]
        if pair in seen:
            raise ValueError("Duplicate hypothesis")
        seen.add(pair)
        for field in ("statement", "semantic_query", "counter_query"):
            h[field] = bounded_text(h.get(field), field, 500)
            if field.endswith("query") and re.search(r"\b(SELECT|MATCH)\s", h[field], re.I):
                raise ValueError("Semantic searches must use natural language, not invented query syntax")
    return hypotheses


def validate_assessment(value, packet):
    if value.get("verdict") not in {"supported", "contradicted", "inconclusive"}:
        raise ValueError("Invalid assessment verdict")
    allowed = {q["id"] for q in packet["queries"]} | {p["id"] for p in packet["passages"]}
    for query in packet["queries"]:
        for row in query.get("rows", []):
            for field, content in row.items():
                if field.endswith("evidence_ids") and isinstance(content, list):
                    allowed.update(content)
                elif field == "evidence_id" and isinstance(content, str):
                    allowed.add(content)
    counter = value.get("counter_evidence")
    if not isinstance(counter, list) or len(counter) > 5:
        raise ValueError("Invalid counter-evidence list")
    for claim in [value.get("interpretation"), *counter]:
        if not isinstance(claim, dict):
            raise ValueError("Cited interpretation required")
        bounded_text(claim.get("text"), "interpretation")
        ids = claim.get("evidence_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in allowed for i in ids):
            raise ValueError("Unrecognized or missing evidence citation; assessment rejected")
    for key in ("recommendation", "next_action", "acceptance_test", "rollback"):
        bounded_text(value.get(key), key)
    for key in ("tradeoffs", "alternatives", "missing_evidence"):
        items = value.get(key)
        if not isinstance(items, list) or len(items) > 8:
            raise ValueError(f"Invalid {key}")
        for item in items:
            bounded_text(item, key, 500)
    if not value["alternatives"] or not value["tradeoffs"]:
        raise ValueError("At least one alternative and tradeoff are required")
    return value


def validated_completion(model, instruction, data, validator):
    for attempt in range(2):
        try:
            value = validator(model.complete(instruction, data))
            emit("model.validation.completed", repaired=bool(attempt), trace_index=len(model.calls)-1 if model.calls else None)
            return value
        except (ValueError, RuntimeError) as exc:
            # One repair for malformed JSON/schema within the global call cap.
            # Transport failures fail promptly rather than repeating a timeout.
            if model.calls:
                model.calls[-1]["validation_error"] = str(exc)
            emit("model.validation.failed", error=str(exc), attempt=attempt+1)
            cause = exc.__cause__
            repairable = isinstance(exc, ValueError) or isinstance(cause, (ValueError, KeyError, TypeError))
            if attempt or not repairable:
                raise
            emit("model.repair.requested", reason=str(exc))
            instruction += "\nPrior output was invalid. Return concise valid JSON, with only allowed identifiers and natural-language searches."


def offline_plan(goal, candidates, count):
    mappings = [("ownership", r"data|table|state|owner|persist"), ("layering", r"layer|controller|boundary|boundaries"),
                ("history", r"history|change|incident|quarter"), ("resilience", r"workflow|retry|availability|blast|remove"),
                ("drift", r"drift|documentation|adr"), ("duplication", r"duplicat|similar|abstraction")]
    family = next((f for f, pattern in mappings if re.search(pattern, goal, re.I)), "coupling")
    return [{"module": name, "family": family,
             "statement": f"{name} may contain an architectural boundary problem relevant to: {goal[:220]}",
             "semantic_query": f"{goal[:300]} business responsibilities and side effects",
             "counter_query": "intentional orchestration cohesive responsibility local transaction atomicity documented boundary exception"}
            for name in candidates[:count]]


def offline_assessment(h, packet):
    module = h["module"]
    directions = {
        "coupling": (f"Evaluate an internal interface separating orchestration from side effects in {module}.",
                     "Identify transaction begin/commit/rollback and caller expectations before extracting any process boundary."),
        "ownership": (f"Verify the authoritative state owner for table references in {module}.",
                      "Resolve table names to physical databases, identify write statements, and characterize concurrent writes before choosing a single writer."),
        "layering": (f"Review dependencies leaving the configured layer of {module}.",
                     "Confirm an allowed dependency rule with the owner; move one violating business decision behind a domain interface if the rule applies."),
        "history": (f"Investigate the strongest co-change relationship involving {module}.",
                    "Review the cited commit window for feature work versus mechanical edits; compare with incident links before prioritizing a boundary change."),
        "resilience": (f"Characterize failure propagation through the bounded dependency paths to {module}.",
                       "Trace one real workflow, simulate dependency failure and retries, and identify which side effect requires idempotency."),
        "drift": (f"Reconcile the declared role of {module} with its current behavior.",
                  "Select a current ADR and a cited dependency; have its owner confirm whether the implementation or documented rule should change."),
        "duplication": (f"Compare the behavior in {module} with graph-adjacent modules before sharing an abstraction.",
                        "Characterize inputs, outputs and invariants for one similar responsibility; share it only if the invariants and ownership match."),
    }
    action_family = {"data_flow": "ownership", "verification": "resilience", "abstraction": "layering", "responsibility": "coupling", "intent_verification": "drift", "runtime": "resilience", "schema_evolution": "ownership", "workflow": "resilience", "incident_analysis": "history", "team_ownership": "history", "configuration": "drift"}.get(h["family"], h["family"])
    recommendation, action = directions[action_family]
    refs = [q["id"] for q in packet["queries"][:2]]
    return {"verdict": "inconclusive",
            "interpretation": {"text": "The executed queries identify review candidates. Offline mode does not judge semantic cohesion or establish a bounded-context split.", "evidence_ids": refs},
            "counter_evidence": [], "recommendation": recommendation, "next_action": action,
            "acceptance_test": f"For the selected seam in {module}, preserve existing behavior in characterization tests, exercise failure/retry behavior, and rerun dependency queries to verify the agreed edge constraint.",
            "rollback": "Keep the original implementation behind a local routing interface and revert that routing change if characterization tests or observed behavior regress.",
            "tradeoffs": ["A new interface adds indirection and maintenance; a process split additionally changes failure and transaction semantics."],
            "alternatives": ["Keep the current module and document its cohesive orchestration role if behavior and transaction evidence support it.",
                             "Extract an in-process capability first when independent deployment is not required."],
            "missing_evidence": ["Neural semantic assessment not executed in offline mode.", "Counter-evidence search results require human interpretation."]}


def investigate(workspace: Path, config: dict, goal: str, offline=False, model=None, snapshot_id=None, progress=None) -> dict:
    bounded_text(goal, "goal", 1000)
    intent_created(goal)
    began = time.perf_counter()
    session = QuerySession(workspace, config, snapshot_id=snapshot_id, progress=progress)
    run_id = current_run().id
    directory = current_run().directory
    event_context(snapshot=session.manifest["id"])
    emit("snapshot.opened", snapshot=session.manifest["id"], repository=session.manifest["repository"])
    model = model or (None if offline else JsonModel(config))
    if session.layers:
        session.layers.model = model
    report = {"id": run_id, "snapshot": session.manifest["id"], "goal": goal, "status": "running",
              "input": session.manifest.get("input", {"kind": "folder", "location": session.manifest["repository"]}),
              "mode": "offline deterministic review" if offline else "model-assisted review",
              "coverage": session.manifest["coverage"], "warnings": session.manifest["warnings"],
              "findings": [], "errors": []}
    try:
        knowledge = KnowledgeBase(config)
        report["knowledge"] = knowledge.audit
        emit("knowledge.loaded", enabled=knowledge.audit["enabled"], version=knowledge.audit["version"],
             sha256=knowledge.audit["sha256"], card_count=len(knowledge.cards))
        if progress:
            progress("discovering")
        hotspots = session.query("hotspots")
        inbound = {r["module"]: r["inbound"] for r in hotspots["rows"]}
        discovery = session.semantic(goal[:500], None)
        semantic_candidates = {r["module"] for r in discovery["rows"] if r["module"] in session.manifest["modules"]}
        # Named module relevance precedes degree; zero-inbound modules remain discoverable.
        words = set(re.findall(r"\w+", goal.casefold()))
        candidates = sorted(session.manifest["modules"],
                            key=lambda m: (-(3 if m.casefold() in goal.casefold() else 0)
                                           - len(words.intersection(re.findall(r"\w+", m.casefold()))) - (1 if m in semantic_candidates else 0),
                                           -inbound.get(m, 0), m))[:12]
        if not candidates:
            raise ValueError("No structural modules indexed. Supply a graph export for non-Python repositories.")
        count = min(config["investigation"]["max_hypotheses"], len(candidates))
        emit("candidates.selected", modules=candidates, max_hypotheses=count)
        if progress:
            progress("planning")
        planning_data = with_guidance(knowledge, config, PLAN,
            {"goal": goal, "candidates": candidates, "families": FAMILIES, "max_hypotheses": count}, goal)
        knowledge.record("planning", planning_data["architecture_guidance"], model_requested=not offline)
        if offline:
            hypotheses = offline_plan(goal, candidates, count)
        else:
            hypotheses = validated_completion(model, PLAN, planning_data,
                                        lambda value: validate_plan(value, candidates, count))
        report["hypotheses"] = hypotheses
        for index, hypothesis in enumerate(hypotheses, 1):
            emit("hypothesis.created", hypothesis_id=f"H{index:02d}", hypothesis=hypothesis,
                 method="offline" if offline else "model")
        for index, hypothesis in enumerate(hypotheses, 1):
            event_context(hypothesis_id=f"H{index:02d}")
            emit("evidence.collection.started")
            if progress:
                progress(f"Collecting evidence for hypothesis {index}/{len(hypotheses)}: {hypothesis['module']}")
            finding = {"id": f"H{index:02d}", "hypothesis": hypothesis, "status": "collecting"}
            report["findings"].append(finding)
            receipts = []
            try:
                unavailable = []
                for tool in FAMILIES[hypothesis["family"]]:
                    try:
                        module_scope = "" if tool in {"schema", "deployment", "configuration", "workflow_states"} else hypothesis["module"]
                        receipts.append(session.query(tool, module_scope))
                    except LayerUnavailable as exc:
                        receipts.append(session.receipts[-1])
                        unavailable.append(f"{tool}: {exc}")
                finding["unavailable_evidence"] = unavailable
                related = []
                for receipt in receipts:
                    for row in receipt["rows"]:
                        related.extend(v for k, v in row.items() if k in {"source", "target", "other_module", "peer"}
                                       and isinstance(v, str) and v in session.manifest["modules"])
                scope = list(dict.fromkeys([hypothesis["module"], *related]))[:6]
                receipts.append(session.semantic(hypothesis["semantic_query"], [hypothesis["module"]], purpose="support"))
                receipts[-1]["purpose"] = "support"
                receipts.append(session.semantic(hypothesis["counter_query"], [hypothesis["module"], "__documents__"], purpose="counter"))
                receipts[-1]["purpose"] = "counter"
                # Per-hypothesis calls, never a full-report context accumulation.
                data = with_guidance(knowledge, config, ASSESS,
                    {"goal": goal, "hypothesis": hypothesis, "packet": {}}, goal, hypothesis["family"], reserve=2400)
                finding["knowledge_ids"] = knowledge.record(finding["id"], data["architecture_guidance"], model_requested=not offline)
                available = evidence_room(config, ASSESS, data)
                if available < 600:
                    raise ValueError("Context cannot accommodate a useful evidence packet; shorten goal or increase budget")
                packet = session.packet(receipts, min(4400, available))
                finding["packet"] = packet
                emit("evidence.packet.created", query_ids=[q["id"] for q in packet["queries"]],
                     evidence_ids=[p["id"] for p in packet["passages"]], omitted_items=packet["omitted_items"])
                data["packet"] = packet
                emit("assessment.started", method="offline" if offline else "model")
                if progress:
                    progress(f"Assessing hypothesis {index}/{len(hypotheses)} ({'offline' if offline else 'model'})")
                if offline:
                    assessment = validate_assessment(offline_assessment(hypothesis, packet), packet)
                else:
                    assessment = validated_completion(model, ASSESS, data,
                        lambda value: validate_assessment(value, packet))
                if hypothesis["family"] == "layering" and assessment["verdict"] == "supported":
                    assessment["verdict"] = "inconclusive"
                    assessment["missing_evidence"].append("No allowed-dependency rule was supplied to this investigation; configured layer names alone do not establish a violation.")
                if unavailable:
                    assessment["verdict"] = "inconclusive"
                    assessment["missing_evidence"] = list(dict.fromkeys([*assessment["missing_evidence"], *unavailable]))
                finding.update(status="assessed", assessment=assessment)
                emit("assessment.completed", assessment=assessment)
                finding["confidence"] = "limited: static evidence; interpretation requires review"
                finding["query_ids"] = [r["id"] for r in receipts]
                finding["evidence_ids"] = list(dict.fromkeys(e for r in receipts for e in session.evidence_ids(r)))
                exact_degree = next((r["rows"][0]["inbound_dependency_pairs"] for r in receipts
                                     if r["tool"] == "inbound_count" and r["rows"]), None)
                finding["priority_basis"] = {"exact_inbound_pairs": exact_degree,
                                             "method": "Goal relevance chosen during planning; degree is exposure, not business value or severity"}
            except Exception as exc:
                finding.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                emit("assessment.failed", error=finding["error"])
                report["errors"].append(f"{finding['id']}: {finding['error']}")
        event_context(hypothesis_id=None)
        assessed = [f for f in report["findings"] if f["status"] == "assessed"]
        if not offline and assessed:
            # Independent final review of the lead candidate against retrieved evidence.
            # Draft hypotheses are not themselves evidence, and never enter the factual packet.
            lead = assessed[0]
            event_context(hypothesis_id=lead["id"])
            emit("review.started")
            declarations = session.query("symbols", lead["hypothesis"]["module"])
            selected = [r for r in session.receipts if r["id"] in lead["query_ids"]] + [declarations]
            review_instruction = ASSESS + "\nIndependently review the lead candidate and produce the final advice. Treat prior proposal as unverified. Reject unjustified extraction, invented callers, and any claim that a database transaction rolls back external effects. If evidence is incomplete, recommend a precise characterization or failure-injection test before structural change. Counter-evidence must be an observed code/document signal, not a hypothetical cost."
            data = with_guidance(knowledge, config, review_instruction,
                {"goal": goal, "hypothesis": lead["hypothesis"],
                 "prior_proposal": lead["assessment"]["recommendation"][:500], "packet": {}},
                goal, lead["hypothesis"]["family"], reserve=2000)
            knowledge.record("final_review", data["architecture_guidance"], model_requested=True)
            available = evidence_room(config, review_instruction, data)
            if available < 800:
                raise ValueError("Insufficient context for independent final review")
            packet = session.packet(selected, min(4400, available))
            data["packet"] = packet
            emit("evidence.packet.created", stage="final_review", query_ids=[q["id"] for q in packet["queries"]],
                 evidence_ids=[p["id"] for p in packet["passages"]], omitted_items=packet["omitted_items"])
            if progress:
                progress("reviewing")
            report["decision"] = validated_completion(model, review_instruction, data, lambda value: validate_assessment(value, packet))
            decision = report["decision"]
            decision["finding_id"] = lead["id"]
            decision["knowledge_ids"] = [c["id"] for c in data["architecture_guidance"]]
            if lead["hypothesis"]["family"] == "layering" and decision["verdict"] == "supported":
                decision["verdict"] = "inconclusive"
                decision["missing_evidence"].append("Configured layer names alone do not establish an allowed-dependency rule.")
            if lead.get("unavailable_evidence"):
                decision["verdict"] = "inconclusive"
                decision["missing_evidence"] = list(dict.fromkeys([*decision["missing_evidence"], *lead["unavailable_evidence"]]))
            if decision["verdict"] == "inconclusive":
                # An unresolved hypothesis may select a validation action, not a refactor.
                # Keep the complete model draft so this policy is transparent and reviewable.
                decision["model_review"] = json.loads(json.dumps(decision))
                action = offline_assessment(lead["hypothesis"], packet)
                for field in ("recommendation", "next_action", "acceptance_test", "rollback", "tradeoffs", "alternatives"):
                    decision[field] = action[field]
                decision["recommendation"] = f"Validate the {lead['hypothesis']['family']} hypothesis in {lead['hypothesis']['module']} before implementing a structural change."
                decision["rollback"] = "The first action adds characterization tests and observations only. Remove the test harness if it is unhelpful; preserve the existing implementation until the agreed acceptance criteria support a change."
                decision["interpretation"] = {"text": "The executed evidence does not establish a justified structural change. The next action is a validation step selected by the investigation family; the unverified model review is retained in report.json.",
                                               "evidence_ids": [selected[0]["id"]]}
                retry_names = [r["symbol"] for r in declarations["rows"] if "retry" in r["symbol"].lower()]
                if retry_names:
                    names = ", ".join(retry_names)
                    decision["recommendation"] = f"Characterize retry and transaction failure behavior in {lead['hypothesis']['module']} before choosing a service boundary."
                    decision["next_action"] = f"Add failure-injection tests around {names}: fail before and after each identified side effect and local commit, then repeat the same logical operation. Record which external effects and stored writes repeat; confirm the actual idempotency contract before changing the boundary."
                    decision["acceptance_test"] = "Produce a failure matrix recording stored state and external-effect counts after the first attempt and retry. Agree expected same-operation behavior with the owner; test local database atomicity separately from external-effect deduplication. A local rollback must not be assumed to reverse an external effect."
                    decision["interpretation"] = {"text": f"The declaration query identifies retry entry points: {names}. Static source and dependency evidence leave operational idempotency and a service split unresolved. The recommended first step measures that behavior without introducing another process boundary.",
                                                   "evidence_ids": [declarations["id"]]}
                    decision["counter_evidence"] = []
                    for passage in packet["passages"]:
                        statements = [line.strip() for line in passage["text"].splitlines()
                                      if re.search(r"local.*transaction|intentionally.*orchestrat", line, re.I)]
                        if statements and len(decision["counter_evidence"]) < 2:
                            decision["counter_evidence"].append({"text": "The source states a constraint to check before splitting (not runtime verification): " + statements[0],
                                                                 "evidence_ids": [passage["id"]]})
                    decision["tradeoffs"] = ["A failure-injection harness takes engineering effort and needs faithful dependency doubles or a controlled integration environment.",
                                             "A remote split introduces failure and consistency decisions that these static queries do not resolve."]
                    decision["alternatives"] = ["Keep the current orchestration if characterization shows coherent responsibilities and safe retries.",
                                                "Introduce an in-process capability seam after tests identify a responsibility that can move without weakening existing invariants."]
                decision["policy"] = "Inconclusive conclusions receive a bounded validation action; model-proposed refactors are not promoted to final advice."
            report["decision"]["focus"] = lead["hypothesis"]["module"]
            report["decision"]["packet"] = packet
            emit("review.completed", verdict=report["decision"]["verdict"],
                 recommendation=report["decision"]["recommendation"], next_action=report["decision"]["next_action"],
                 policy=report["decision"].get("policy"),
                 decision={k: v for k, v in report["decision"].items() if k not in {"packet", "model_review"}})
        event_context(hypothesis_id=None)
        report["status"] = "partial" if report["errors"] else "review_draft"
    except Exception as exc:
        report["status"] = "failed"
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        emit("investigation.failed", error=report["errors"][-1])
    finally:
        event_context(hypothesis_id=None)
        if progress:
            progress("saving_report")
        report["queries"] = session.receipts
        report["materializations"] = session.materializations
        used_ids = {eid for r in session.receipts for eid in session.evidence_ids(r)}
        report["evidence"] = {eid: session.evidence[eid] for eid in sorted(used_ids)}
        report["metrics"] = {"investigation_ms": round((time.perf_counter() - began) * 1000, 2),
                             "queries": len(session.receipts), "query_ms": sum(r["elapsed_ms"] for r in session.receipts),
                             "llm_calls": len(model.calls) if model else 0,
                             "graph_build_ms": sum(e.get("build_ms", 0) for e in session.materializations),
                             "layer_model_calls": sum(e.get("model_calls", 0) for e in session.materializations)}
        report["report_directory"] = str(directory.resolve())
        report["artifacts"] = {"report": "report.md", "prompts": "suggestive_prompts.md",
                               "knowledge": "knowledge.json", "data": "report.json", "model_trace": "model-trace.json", "events": "events.log"}
        for filename, value in (("investigation.json", report), ("model-trace.json", model.calls if model else [])):
            (directory / filename).write_text(json.dumps(value, indent=2), encoding="utf-8")
    if progress:
        progress(f"Report saved ({report['status']}): {directory.resolve() / 'report.md'}")
    return report

