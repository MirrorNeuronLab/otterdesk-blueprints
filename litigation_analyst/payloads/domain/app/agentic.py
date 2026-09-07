"""LLM-selected enquiries with durable decisions and explicit hypothesis revisions."""

import json
from mn_prototype_bounded_tool_loop_agent.checkpoint import CheckpointLoop, fingerprint
from .instructions import SYSTEM, GRAPH_SCHEMA
from .guidance import InvestigationGuidance
from .planning import PLAN, OUTCOME, HYPOTHESIS, PHASE_INSTRUCTIONS
from .findings import REPORT, REVIEW
from .actions import InvestigationActions
from mn_prototype_bounded_tool_loop_agent.phases import PhaseCycle
from mn_sdk.agent_events import emit_agent_event
from .local_llm import SDKInvestigationModel
from .skill_bindings import bind_skills
from .activity import observe_action
from .prompt_context import investigation_history
from ..evidence.store import EvidenceStore


def run_investigation(case, corpus, receipt, context, llm_client=None, *, declared):
    guidance = InvestigationGuidance()
    try:
        return _run_investigation(
            case,
            corpus,
            receipt,
            context,
            llm_client,
            declared=declared,
            guidance=guidance,
        )
    finally:
        guidance.index.close()


def _run_investigation(
    case, corpus, receipt, context, llm_client=None, *, declared, guidance
):
    policy = context["config"]["investigation"]
    model = SDKInvestigationModel(llm_client)
    store = EvidenceStore(case / "evidence.sqlite3")
    store.add_sources(corpus.scan())
    # Stable key prevents orphan duplicate investigations across checkpoint initialization.
    existing = store.query_readonly("SELECT id FROM investigations ORDER BY id")
    investigation_id = (
        existing[0]["id"]
        if existing
        else store.create_investigation(
            context["payload"]["goal"],
            corpus.access_scope,
            llm_model=model.model,
            graph_path=case / "evidence.rgx",
        )
    )
    runtime = bind_skills(case, corpus, store, investigation_id, declared)
    manuals = {
        skill["id"]: runtime.read_skill(skill["id"])["sha256"]
        for skill in runtime.list_skills()
    }
    runtime.read_hashes.clear()  # Host fingerprinting does not count as the agent reading a manual.
    loop = CheckpointLoop(
        case / "agent_checkpoint.json",
        {
            "receipt": receipt,
            "config": context["config"],
            "goal": context["payload"]["goal"],
            "model": model.model,
            "manuals": manuals,
            "descriptors": runtime.descriptors,
            "prompt": fingerprint(
                SYSTEM
                + GRAPH_SCHEMA
                + PHASE_INSTRUCTIONS
            ),
            "guidance": guidance.fingerprint,
        },
        max_decisions=policy["max_model_decisions"],
        max_invocations=policy["max_skill_invocations"],
        seconds=policy["max_investigation_seconds"],
        finalization_decisions=min(4, policy["max_model_decisions"]),
    )
    data = loop.state["data"]
    cycle = PhaseCycle(data)
    data.setdefault("hypotheses", {})
    data.setdefault("model_interactions", [])
    data.setdefault(
        "source_review_flags",
        {
            d.source_id: "Potential privileged material; human handling decision required."
            for d in corpus.scan()
            if d.text
            and any(
                term in d.text.lower()
                for term in (
                    "attorney-client privileged",
                    "seeking legal representation",
                    "seeking legal advice",
                    "request for legal representation",
                )
            )
        },
    )
    data["investigation_id"] = investigation_id
    for record in loop.state["records"]:
        if (
            record["action"].get("name") == "read_skill"
            and "result" in record
            and "error" not in record["result"]
        ):
            runtime.read_hashes[record["result"]["skill"]] = record["result"]["sha256"]

    execute = InvestigationActions(cycle, policy, runtime, corpus, data, store, investigation_id)

    def progress(state):
        # Audit growth and planning alone are not investigation progress.
        marks = set()
        for record in state["records"]:
            action, result = record.get("action", {}), record.get("result", {})
            if not isinstance(result, dict) or "error" in result or result.get("reused"):
                continue
            if action.get("name") in {"invoke_skill", "read_skill", "review_enquiry"}:
                if action.get("name") == "review_enquiry" and not result.get("outcome", {}).get("evidence_ids"):
                    continue
                value = dict(result)
                if isinstance(value.get("outcome"), dict):
                    value["outcome"] = {k: v for k, v in value["outcome"].items() if k != "plan_index"}
                marks.add(fingerprint(value))
        accepted = set(state["data"].get("report_review", {}).get("accepted_ids", []))
        for finding in state["data"].get("report_draft", {}).get("findings", []):
            if finding["id"] in accepted:
                marks.add(fingerprint({"reviewed_finding": finding["id"], "evidence_ids": finding["evidence_ids"]}))
        return sorted(marks)

    def propose(state):
        # Full audit remains on disk; send bounded recent observations and current hypotheses.
        remaining = policy["max_model_decisions"] - len(state["records"])
        synthesis = (
            remaining <= 4
            or sum(r["action"].get("name") == "invoke_skill" for r in state["records"])
            >= policy["max_skill_invocations"]
        )
        active = cycle.state["plans"][-1] if cycle.state["plans"] else {}
        phase = "report_review" if "pending_review_ids" in data else cycle.phase
        knowledge = guidance.retrieve(
            phase, json.dumps(active or {"goal": context["payload"]["goal"]})
        )
        emit_agent_event(
            "investigation_phase",
            {
                "message": f"{phase}: {active.get('question', 'review findings and choose an enquiry')}"[
                    :900
                ]
            },
        )
        allowed = execute.allowed_actions(state)
        request = {
            "control": {
                "phase": phase, "active_plan": active, "allowed_actions": allowed,
                "latest_error": state["records"][-1].get("result", {}).get("error") if state["records"] else None,
                "recovery": state.get("progress_guard", {}).get("recovery"),
                "instruction": "Choose only an allowed action. In execution, read an appropriate skill manual before invoking its operations. An empty approved_operations map means no manual has yet been read; it does not mean no skills exist.",
            },
            "goal": context["payload"]["goal"],
            "phase": phase,
            "synthesis_only": synthesis,
            "active_plan": active,
            "completed_enquiries": cycle.state["outcomes"][-20:],
            "past_enquiry_questions": [p["question"] for p in cycle.state["plans"]][
                -50:
            ],
            "actions_before_review": max(0, cycle.max_actions - cycle.state["actions"]),
            "guidance": knowledge,
            "report_draft": data.get("report_draft"),
            "report_review": data.get("report_review"),
            "source_review_flags": data["source_review_flags"],
            "derivations": data.get("derivations", [])[-5:],
            "graph_schema": GRAPH_SCHEMA,
            "source_inventory": [
                {"id": d.source_id, "type": d.media_type} for d in corpus.scan()
            ][:50],
            "skills": runtime.list_skills(),
            "action_schemas": {
                "plan_enquiry": PLAN,
                "review_enquiry": OUTCOME,
                "update_hypothesis": HYPOTHESIS,
                "submit_report": REPORT,
                "review_report": REVIEW,
            },
            "read_manual_hashes": dict(runtime.read_hashes),
            "approved_operations": {
                key: {
                    name: spec["arguments"]
                    for name, spec in descriptor["operations"].items()
                    if (key, name) in runtime.bindings
                }
                for key, descriptor in runtime.descriptors.items()
                if key in runtime.read_hashes
            },
            "hypotheses": list(data["hypotheses"].values())[-40:],
            "history": investigation_history(state["records"]),
            "history_is_complete": False,
            "decisions_remaining": policy["max_model_decisions"]
            - len(state["records"]),
        }
        request["action_schemas"] = {k: v for k, v in request["action_schemas"].items() if k in allowed}
        if phase == "report_review":
            pending = [
                f
                for f in data["report_draft"]["findings"]
                if f["id"] in data["pending_review_ids"]
            ]
            request["report_draft"] = {"findings": pending}
            cited = {i for f in pending for i in f["evidence_ids"]}
            request["review_evidence"] = [
                dict(evidence_id=e.evidence_id, source_id=e.source_id, text=e.text)
                for e in store.evidence_for(investigation_id)
                if e.evidence_id in cited
            ]
        messages = [
            {"role": "system", "content": SYSTEM + PHASE_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
        ]
        try:
            response = model.complete_json(messages)
        except Exception as exc:
            data["model_interactions"].append(
                {
                    "request": messages,
                    "error": str(exc)[:1000],
                    "response": getattr(exc, "response", None),
                }
            )
            raise
        data["model_interactions"].append(
            {"request": response.request, "response": response.response}
        )
        return response.value

    state = loop.run(
        propose,
        lambda action, state: observe_action(action, state, execute),
        cancelled=lambda: (case / "cancel.request").exists(),
        allowed_actions=execute.allowed_actions,
        progress=progress,
        event_sink=lambda event: emit_agent_event(event["type"], {
            "message": event["type"].replace("_", " ") + ": " + event["reason"],
            "reason": event["reason"], "category": "agent",
        }),
    )
    return state, store
