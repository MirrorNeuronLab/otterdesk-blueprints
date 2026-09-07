"""Bounded specialist operations for a committed architecture round."""
from .catalog import LayerUnavailable
from .events import audit_scope
from .graph import QuerySession
from .investigation_store import (
    BudgetExhausted,
    InvestigationStore,
    RecordedModel,
    task_input,
)
from .investigator import (
    ASSESS,
    offline_assessment,
    validate_assessment,
    validated_completion,
)
from .knowledge import KnowledgeBase, evidence_room, with_guidance


def task_key(work):
    return f"r{work['revision']:02d}-{work['node_key']}"


def packet_for(records, byte_limit=4400):
    session = object.__new__(QuerySession)
    session.evidence = {key: value for record in records for key, value in record["evidence"].items()}
    receipts = [q for record in records for q in record["queries"]]
    packet = session.packet(receipts, byte_limit)
    # Expand already cited witnesses before inventing another retrieval task. Full
    # immutable spans remain in the evidence ledger when the prompt cannot fit them.
    import json
    for passage in packet["passages"]:
        previous = dict(passage)
        passage["text"] = session.evidence[passage["id"]]["text"]
        passage["excerpt_truncated"] = False
        if len(json.dumps(packet, ensure_ascii=False).encode()) > byte_limit:
            passage.clear()
            passage.update(previous)
    return packet


def collect(context, work, *, semantic=False, llm_client=None):
    store = InvestigationStore(context["run_dir"])
    work = task_input(store, work)
    store.load_ref(work["context"])
    key = task_key(work)
    path = f"investigation/observations/{key}.json"
    if store.path(path).exists():
        return {"observation": store.write(path, store.read(path))}
    h = work["hypothesis"]
    record = {"id": key, "revision": work["revision"], "hypothesis_id": h["id"],
              "queries": [], "evidence": {}, "materializations": [], "unavailable": []}
    session = None
    try:
        store.reserve("queries")
        with audit_scope(store.root / "investigation/activity" / key):
            session = QuerySession(store.root / "evidence", store.config, snapshot_id=store.read("snapshot.json")["id"])
            if session.layers:
                session.layers.model = None if store.config["offline"] else RecordedModel(store, key, llm_client)
            if semantic:
                purpose = work["purpose"]
                text = h["semantic_query"] if purpose == "support" else h["counter_query"]
                modules = [h["module"]] + (["__documents__"] if purpose == "counter" else [])
                session.semantic(text, modules, purpose=purpose)
            else:
                tool = work["tool"]
                scope = "" if tool in {"schema", "deployment", "configuration", "workflow_states", "hotspots"} else h["module"]
                session.query(tool, scope)
    except (LayerUnavailable, BudgetExhausted) as exc:
        record["unavailable"].append(str(exc))
        if isinstance(exc, BudgetExhausted):
            record["budget_stop"] = str(exc)
    if session:
        for q in session.receipts:
            q["id"] = key + "-" + q["id"]
        record["queries"] = session.receipts
        used = {eid for q in session.receipts for eid in session.evidence_ids(q)}
        record["evidence"] = {eid: session.evidence[eid] for eid in sorted(used)}
        record["materializations"] = session.materializations
        record["coverage"] = session.manifest["coverage"]
    return {"observation": store.write(path, record)}


def query_graph(context, work, *, llm_client=None):
    return collect(context, work, llm_client=llm_client)


def search_evidence(context, work, *, llm_client=None):
    return collect(context, work, semantic=True, llm_client=llm_client)


def validate_advice(value, packet, unavailable=(), *, final_review=False):
    validate_assessment(value, packet)
    if unavailable and value["verdict"] != "inconclusive":
        raise ValueError("Unavailable evidence requires an inconclusive verdict and verification task")
    kind = value.get("action_kind")
    if kind not in {"verify", "preserve", "change"}:
        raise ValueError("Advice needs verify, preserve or change action_kind")
    if final_review and value.get("missing_evidence") and kind == "change":
        raise ValueError("Decisive evidence gaps require verification before a structural change; preserve concrete project-specific reasoning")
    if value["verdict"] == "inconclusive" and kind != "verify":
        raise ValueError("Inconclusive advice must propose verification before structural change")
    if value["verdict"] == "contradicted" and kind == "change":
        raise ValueError("Contradicted findings cannot recommend structural change")
    return value


def verification_policy(value):
    if value.get("action_kind") == "verify":
        for field in ("recommendation", "next_action", "acceptance_test"):
            value["model_" + field] = value[field]
        unknowns = value.get("missing_evidence") or [value["next_action"]]
        value["recommendation"] = "Verify the decisive unknowns before implementing this conditional proposal: " + value["recommendation"]
        value["next_action"] = "Resolve the following questions using the cited source, provider contracts, and an isolated characterization harness; do not modify application behavior in this phase: " + " ".join(unknowns)
        value["acceptance_test"] = "For each listed question, retain the exact source or contract citation and a reproducible pass/fail observation from the characterization harness. Record preconditions and observed effects. Any unresolved question keeps the implementation proposal deferred."
        value["model_rollback"] = value["rollback"]
        value["rollback"] = "Remove only instrumentation or tests added for this verification task; preserve existing application code and all pre-existing changes."
    return value


def assess_hypothesis(context, work, *, llm_client=None):
    store = InvestigationStore(context["run_dir"])
    work = task_input(store, work)
    store.load_ref(work["context"])
    key = task_key(work)
    h = work["hypothesis"]
    path = f"investigation/findings/{key}.json"
    if store.path(path).exists():
        return {"finding": store.write(path, store.read(path))}
    records = [r for r in store.results() if r["revision"] == work["revision"] and r["hypothesis_id"] == h["id"]]
    unavailable = [reason for r in records for reason in r["unavailable"]]
    finding = {"id": h["id"], "revision": work["revision"], "hypothesis": h, "status": "incomplete",
               "unavailable_evidence": unavailable, "query_ids": [q["id"] for r in records for q in r["queries"]],
               "evidence_ids": sorted({eid for r in records for eid in r["evidence"]}),
               "confidence": "Static evidence; runtime behavior remains unverified"}
    if any(r.get("budget_stop") for r in records):
        finding["error"] = "Evidence collection stopped at the investigation budget"
    else:
        knowledge = KnowledgeBase(store.config)
        instruction = ASSESS + "\nInclude action_kind: verify, preserve, or change. Inconclusive advice must be a specific verification task. For verification-only work, rollback removes only newly added instrumentation or harnesses; never revert existing repository changes."
        data = with_guidance(knowledge, store.config, instruction,
            {"goal": store.context["payload"]["goal"], "hypothesis": h, "packet": {}, "review_policy": True},
            store.context["payload"]["goal"], h["family"], reserve=2400)
        packet = packet_for(records, min(9000, evidence_room(store.config, instruction, data)))
        finding["packet"] = packet
        finding["knowledge_ids"] = knowledge.record(h["id"], data["architecture_guidance"], model_requested=not store.config["offline"])
        data["packet"] = packet
        # Missing views/rules are supplied to the model before it chooses an action.
        if h["family"] == "layering":
            unavailable.append("No verified allowed-dependency rule was supplied")
        data["unavailable_evidence"] = unavailable
        if unavailable:
            instruction += "\nRequired evidence is unavailable: verdict must be inconclusive and action_kind verify."
        try:
            if store.config["offline"]:
                value = offline_assessment(h, packet)
                value.update(action_kind="verify", recommendation=f"Verify the {h['family']} hypothesis in {h['module']} before any structural change.")
            else:
                model = RecordedModel(store, key, llm_client)
                value = validated_completion(model, instruction, data, lambda v: validate_advice(v, packet, unavailable))
            if unavailable and value["verdict"] != "inconclusive":
                raise ValueError("Unavailable evidence cannot support a conclusive assessment")
            finding.update(status="assessed", assessment=verification_policy(validate_advice(value, packet)), knowledge=knowledge.audit)
        except BudgetExhausted as exc:
            finding["error"] = str(exc)
    return {"finding": store.write(path, finding)}


def summarize_round(context, work, *, llm_client=None):
    store = InvestigationStore(context["run_dir"])
    work = task_input(store, work)
    findings = store.findings()
    summary = {"revision": work["revision"], "findings": [{"id": f["id"], "status": f["status"],
        "verdict": f.get("assessment", {}).get("verdict"), "missing_evidence": f.get("assessment", {}).get("missing_evidence", []),
        "counter_evidence": f.get("assessment", {}).get("counter_evidence", [])} for f in findings], "usage": store.usage()}
    return {"summary": store.write(f"investigation/rounds/{work['revision']:02d}.json", summary)}
