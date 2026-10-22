"""Publish verified task artifacts and adopt only completed Harness2 memory."""
from mn_sdk.agent_events import report_activity
from mn_sdk.artifact_handoff import relative_path
from mn_sdk.integrations.block_publication_files import publish_files
from mn_sdk_common.publication import ArtifactWrite

from .configuration import read_value, settings
from .memory import adopt
from .conversation import Conversation


def publish(block, inputs):
    block.check()
    previous = read_value(block, inputs["previous"])
    checkpoint = read_value(block, previous["outcome"])
    result = checkpoint["data"]
    if result["job_id"] != block.job_id or result["run_id"] != block.run_id:
        raise ValueError("Harness2 result belongs to another Job or run")
    # Verify every exported artifact before retaining any new memory.
    for name, ref in result["deliverables"].items():
        relative_path(name)
        if ref["path"] != "deliverables/" + name:
            raise ValueError("Unexpected Harness2 deliverable path")
        block.store.read_bytes(ref)
    answer = block.store.read_bytes(result["answer"])
    audit = block.store.read(result["improvement"])
    snapshot = block.store.read(result["memory"])
    receipt = None
    if result["status"] == "completed":
        receipt = adopt(block, snapshot, expected_generation=result["expected_generation"],
                        request_id=result["request_id"], limits=settings(block))
    public = {key: result[key] for key in ["schema_version", "status", "job_id", "run_id", "request_id"]}
    public.update(answer="answer.md", deliverables=[ref["path"] for ref in result["deliverables"].values()],
                  improvement={"audit": "harness-audit.json", "memory_retained": receipt is not None,
                               "generation": receipt["generation"] if receipt else result["expected_generation"],
                               "model_weights_updated": False})
    references = {
        "result": block.store.commit("result.json", public).to_dict(),
        "answer": block.store.commit_bytes("answer.md", answer, kind="markdown").to_dict(),
        "audit": block.store.commit("harness-audit.json", audit, kind="harness_audit").to_dict(),
        "deliverables": result["deliverables"],
    }
    selected = [references["result"], references["answer"], references["audit"],
                *references["deliverables"].values()]
    publication = publish_files(block, [
        ArtifactWrite(str(index), ref["path"], block.store.read_bytes(ref), kind=ref["kind"])
        for index, ref in enumerate(selected)
    ], name="task-results")
    # Runtime output staging and host-folder delivery remain SDK/Core responsibilities.
    report_activity("Task result published; private Harness2 memory retained" if receipt else
                    "Harness2 could not complete this task; previous memory preserved", kind="result",
                    step_id=block.step_id, run_dir=block.store.run_dir)
    Conversation(block).notice("result", "Your results are ready in the output folder. Review answer.md for checks and limitations."
        if receipt else "I couldn’t complete this task. Review answer.md and the audit in the output folder before trying again.")
    return {"status": result["status"], "artifacts": references, "published_files": publication}
