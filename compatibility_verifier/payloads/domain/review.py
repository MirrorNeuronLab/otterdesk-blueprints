"""Workflow hooks for the compatibility verification domain."""
from mn_sdk.blueprint.inputs import capture_declared_inputs
from mn_sdk.blueprint.wasm import invoke_component
from mn_comparison_evidence_skill import evidence_blocks, read_ledger, receive_files, select
from mn_sdk.blueprint.services import RunMailbox
from mn_verification_checks_skill import assignment, digest, execute, make_plan, report_document
from .wit_verification import assess, capture_subject, reconcile

ROLE = "compatibility"
CATEGORY = "boundary"
SECTION = "Integration and regression"


def capture(block, inputs):
    config = block.original_config.get("inputs", {}).get("payload", {})
    managed = bool(config.get("collaboration_group_id") and config.get("collaboration_peers"))
    if managed:
        with RunMailbox.open(block) as mailbox:
            message = mailbox.next_assignment(block)
            if message:
                handoff = mailbox.read_attachment(message)
                if (message["sender_blueprint_id"] != "software_verifier_suite"
                        or handoff.get("schema") != "software-verification.assignment.v1"
                        or handoff.get("role") != ROLE or handoff.get("recipient_job_id") != mailbox.job_id
                        or any(c["specialist"] != ROLE for c in handoff["plan"]["checks"])):
                    raise ValueError("The verification assignment does not match this specialist.")
                plan = handoff["plan"]
                selected = handoff.get("observations", {"digest": None, "cases": [], "coverage": None})
                if (digest({k: v for k, v in plan.items() if k != "plan_id"}) != plan["plan_id"]
                        or invoke_component("snapshot", {"sources": handoff["sources"]}, environment=block.environment)["subject"] != plan["subject"]
                        or (plan.get("observation_scope") and plan["observation_scope"] != digest(selected))
                        or any(row["category"] != CATEGORY for row in selected["cases"])):
                    raise ValueError("The evidence differs from the approved assignment.")
                receive_files(plan, handoff.get("evidence_files", {}),
                              lambda ref: mailbox.read_attachment({**message, "attachment": ref}),
                              lambda name, data: block.store.commit_bytes("assigned-evidence/" + name, data, kind="runner_receipt"))
                return {"assignment": message,
                        "observations": block.store.commit("case-observations.json", selected).to_dict(),
                        "plan": block.store.commit("verification-plan.json", handoff["plan"]).to_dict(),
                        "sources": block.store.commit("source-snapshot.json", handoff["sources"]).to_dict(),
                        "baseline": block.store.commit("baseline-snapshot.json", handoff["baseline"]).to_dict()
                                    if handoff["baseline"] is not None else None}
    request = capture_declared_inputs(block, inputs, runtime_file=__file__)
    if not request.get("input_folder"):
        if managed:
            return {"waiting_for_assignment": True}
        raise ValueError("Choose a source folder for a standalone review or join Software verifier suite for assignments.")
    staging = next(s for s in block.original_config["local_inputs"]["folders"]
                   if s["config_path"] == "inputs.payload.input_folder")
    sources, omitted, comparison, baseline = capture_subject(block, request["input_folder"], staging["allowed_extensions"])
    plan = make_plan(sources, request.get("verification_scope"), run_id=block.run_id, specialist=ROLE,
                     comparison=comparison, baseline_sources=baseline, omitted=omitted, evidence_folder=request.get("evidence_folder"))
    selected = select(read_ledger(request.get("evidence_folder"), request.get("assurance_evidence_sha256"), plan, sources), CATEGORY)
    return {"observations": block.store.commit("case-observations.json", selected).to_dict(),
            "plan": block.store.commit("verification-plan.json", plan).to_dict(),
            "sources": block.store.commit("source-snapshot.json", sources).to_dict(),
            "baseline": block.store.commit("baseline-snapshot.json", baseline).to_dict() if baseline is not None else None}


def inspect(block, inputs):
    packet = inputs["previous"]
    if packet.get("waiting_for_assignment"):
        return {
            "document": {"title": "Waiting for an assignment", "identity": block.run_id,
                         "summary": "Software verifier suite has no assignment queued for this co-worker.", "sections": []},
            "data": {"final_artifact": {"schema_version": "mn.verification.v1.report", "status": "waiting_for_assignment",
                                        "verdict": "INCONCLUSIVE", "plan": None, "checks": [], "findings": [], "blockers": []}},
        }
    plan = block.store.read(packet["plan"])
    sources = block.store.read(packet["sources"])
    baseline = block.store.read(packet["baseline"]) if packet.get("baseline") else None
    folder = (block.store.path("assigned-evidence")
              if packet.get("assignment") else block.store.read_path("inputs.json").get("evidence_folder"))
    records = []
    for check in plan["checks"]:
        for number in (1, 2):
            task = assignment(plan, check["id"], number)
            path = f"verification-attempts/{check['id']}-{number}.json"
            ref = block.freeze_checkpoint(path, lambda: execute(plan, task, sources, specialist=ROLE,
                baseline_sources=baseline, evidence_folder=folder))
            record = block.read_checkpoint(ref, expected_path=path)
            records.append(record)
            if not record["retryable"]:
                break
    report = reconcile(block, plan, records)
    selected = block.store.read(packet["observations"])
    aspect = assess(block, selected, test_sources=sources if CATEGORY == "test_control" else None, paths=plan["paths"])
    report["aspect"] = aspect
    if any(row["status"] == "unmet" for row in aspect["cases"]):
        report["verdict"] = "FAIL"
    elif any(row["status"] != "met" for row in aspect["cases"]) and report["verdict"] == "PASS":
        report["verdict"] = "INCONCLUSIVE"
    if message := packet.get("assignment"):
        with RunMailbox.open(block) as mailbox:
            mailbox.reply(message, subject=f"{ROLE.capitalize()} verification · {report['verdict']}",
                          text=f"{SECTION} · {len(aspect['cases'])} recorded cases and {len(report['checks'])} checks.",
                          value={"assignment_id": message["id"], "plan": plan, "records": records, "aspect": aspect})
    document = report_document(report, SECTION, role=ROLE)
    blocks = evidence_blocks(aspect)
    if blocks:
        document["sections"].insert(0, {"id": "aspect", "title": SECTION, "blocks": blocks})
    return {"document": document, "data": {"final_artifact": report}}
