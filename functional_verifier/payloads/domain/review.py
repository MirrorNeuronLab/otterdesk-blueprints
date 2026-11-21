"""Workflow hooks for the functional verification domain."""
from mn_sdk.blueprint.inputs import capture_declared_inputs, configured_input_path
from mn_sdk.blueprint.services import RunMailbox
from mn_verification_checks_skill import assignment, capture_subject, execute, make_plan, reconcile, report_document

ROLE = "functional"


def capture(block, inputs):
    config = block.original_config.get("inputs", {}).get("payload", {})
    managed = bool(config.get("collaboration_group_id") and config.get("collaboration_peers"))
    if managed:
        with RunMailbox.open(block) as mailbox:
            message = mailbox.next_assignment(block)
            if message:
                handoff = mailbox.read_attachment(message)
                if (message["sender_blueprint_id"] != "code_verifier"
                        or handoff.get("schema") != "software-verification.assignment.v1"
                        or handoff.get("role") != ROLE or handoff.get("recipient_job_id") != mailbox.job_id
                        or not handoff["plan"]["checks"] or any(c["specialist"] != ROLE for c in handoff["plan"]["checks"])):
                    raise ValueError("The verification assignment does not match this specialist.")
                return {"assignment": message,
                        "plan": block.store.commit("verification-plan.json", handoff["plan"]).to_dict(),
                        "sources": block.store.commit("source-snapshot.json", handoff["sources"]).to_dict(),
                        "baseline": block.store.commit("baseline-snapshot.json", handoff["baseline"]).to_dict()
                                    if handoff["baseline"] is not None else None}
    request = capture_declared_inputs(block, inputs, runtime_file=__file__)
    if not request.get("input_folder"):
        if managed:
            return {"waiting_for_assignment": True}
        raise ValueError("Choose a source folder for a standalone review or join Software verifier for assignments.")
    staging = next(s for s in block.original_config["local_inputs"]["folders"]
                   if s["config_path"] == "inputs.payload.input_folder")
    sources, omitted, comparison, baseline = capture_subject(request["input_folder"],
        suffixes=staging["allowed_extensions"], check=block.check)
    plan = make_plan(sources, request.get("verification_scope"), run_id=block.run_id, specialist=ROLE,
                     comparison=comparison, baseline_sources=baseline, omitted=omitted, evidence_folder=request.get("evidence_folder"))
    return {"plan": block.store.commit("verification-plan.json", plan).to_dict(),
            "sources": block.store.commit("source-snapshot.json", sources).to_dict(),
            "baseline": block.store.commit("baseline-snapshot.json", baseline).to_dict() if baseline is not None else None}


def inspect(block, inputs):
    packet = inputs["previous"]
    if packet.get("waiting_for_assignment"):
        return {
            "document": {"title": "Waiting for an assignment", "identity": block.run_id,
                         "summary": "Software verifier has no assignment queued for this co-worker.", "sections": []},
            "data": {"final_artifact": {"schema_version": "mn.verification.v1.report", "status": "waiting_for_assignment",
                                        "verdict": "INCONCLUSIVE", "plan": None, "checks": [], "findings": [], "blockers": []}},
        }
    plan = block.store.read(packet["plan"])
    sources = block.store.read(packet["sources"])
    baseline = block.store.read(packet["baseline"]) if packet.get("baseline") else None
    folder = (configured_input_path(block.original_config, {}, "evidence_folder", runtime_file=__file__)
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
    report = reconcile(plan, records)
    if message := packet.get("assignment"):
        with RunMailbox.open(block) as mailbox:
            mailbox.reply(message, subject=f"{ROLE.capitalize()} verification · {report['verdict']}",
                          text=f"{len(report['checks'])} checks. {len(report['findings'])} findings.",
                          value={"assignment_id": message["id"], "plan": plan, "records": records})
    return {"document": report_document(report, "Functional verifier", role=ROLE), "data": {"final_artifact": report}}
