"""LLM-selected enquiries with durable decisions and explicit hypothesis revisions."""

import json
from jsonschema import Draft202012Validator
from mn_prototype_bounded_tool_loop_agent.checkpoint import CheckpointLoop, fingerprint
from .instructions import SYSTEM, GRAPH_SCHEMA
from .local_llm import SDKInvestigationModel
from .skill_bindings import bind_skills
from ..evidence.store import EvidenceStore

TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
STRINGS = {"type": "array", "maxItems": 40, "items": TEXT}
HYPOTHESIS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,64}$"},
        "question": TEXT,
        "factual_basis": TEXT,
        "supporting_evidence": STRINGS,
        "contradictory_evidence": STRINGS,
        "alternatives": dict(STRINGS, minItems=1),
        "status": {"enum": ["proposed", "supported", "contradicted", "inconclusive"]},
        "assessment": TEXT,
        "outstanding_enquiries": STRINGS,
        "parent_id": {"type": ["string", "null"]},
    },
    "required": [
        "id",
        "question",
        "factual_basis",
        "supporting_evidence",
        "contradictory_evidence",
        "alternatives",
        "status",
        "assessment",
        "outstanding_enquiries",
        "parent_id",
    ],
}


def run_investigation(case, corpus, receipt, context, llm_client=None, *, declared):
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
            "prompt": fingerprint(SYSTEM + GRAPH_SCHEMA),
        },
        max_decisions=policy["max_model_decisions"],
        max_invocations=policy["max_skill_invocations"],
        seconds=policy["max_investigation_seconds"],
    )
    data = loop.state["data"]
    data.setdefault("hypotheses", {})
    data.setdefault("model_interactions", [])
    data["investigation_id"] = investigation_id
    for record in loop.state["records"]:
        if (
            record["action"].get("name") == "read_skill"
            and "result" in record
            and "error" not in record["result"]
        ):
            runtime.read_hashes[record["result"]["skill"]] = record["result"]["sha256"]

    def propose(state):
        # Full audit remains on disk; send bounded recent observations and current hypotheses.
        request = {
            "goal": context["payload"]["goal"],
            "graph_schema": GRAPH_SCHEMA,
            "source_inventory": [
                {"id": d.source_id, "type": d.media_type} for d in corpus.scan()
            ][:50],
            "skills": runtime.list_skills(),
            "hypotheses": list(data["hypotheses"].values()),
            "history": state["records"][-8:],
            "decisions_remaining": policy["max_model_decisions"]
            - len(state["records"]),
        }
        messages = [
            {"role": "system", "content": SYSTEM},
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

    def execute(action, state):
        name, args = action["name"], action["arguments"]
        if name == "list_skills":
            if args:
                raise ValueError("list_skills takes no arguments")
            return {"skills": runtime.list_skills()}
        if name == "read_skill":
            if set(args) != {"skill"}:
                raise ValueError("read_skill requires only skill")
            return runtime.read_skill(**args)
        if name == "invoke_skill":
            if set(args) != {"skill", "operation", "arguments"}:
                raise ValueError("invalid skill invocation fields")
            return runtime.invoke_skill(**args)
        if name == "update_hypothesis":
            Draft202012Validator(HYPOTHESIS).validate(args)
            evidence_ids = {e.evidence_id for e in store.evidence_for(investigation_id)}
            cited = set(args["supporting_evidence"] + args["contradictory_evidence"])
            if not cited <= evidence_ids:
                raise ValueError("hypothesis contains unverified evidence IDs")
            if args["status"] in ("supported", "contradicted") and not cited:
                raise ValueError(
                    "supported or contradicted hypotheses require source evidence"
                )
            if args["parent_id"] is not None and (
                args["parent_id"] not in data["hypotheses"]
                or args["parent_id"] == args["id"]
            ):
                raise ValueError("unknown or self-referencing parent hypothesis")
            data["hypotheses"][args["id"]] = dict(args)
            return {"hypothesis": args}
        if name == "finish":
            if (
                set(args) != {"reason"}
                or not isinstance(args["reason"], str)
                or not args["reason"].strip()
            ):
                raise ValueError("finish requires a reason")
            if not data["hypotheses"]:
                raise ValueError(
                    "record at least one hypothesis and its limitations before finishing"
                )
            return {"reason": args["reason"]}
        raise ValueError("unknown investigation action")

    state = loop.run(
        propose, execute, cancelled=lambda: (case / "cancel.request").exists()
    )
    return state, store
