"""Publish the observed outcome and a content-free action audit."""
import hashlib

from mn_sdk.agent_events import report_activity
from mn_sdk.context_engine import context_memory_section_enabled
from mn_sdk.integrations.block_publication_files import publish_files
from mn_sdk_common.publication import ArtifactWrite

from .configuration import read_value
from .conversation import Conversation


def publish(block, inputs):
    block.check()
    previous = read_value(block, inputs["previous"])
    result = read_value(block, previous["outcome"])["data"]
    if result["job_id"] != block.job_id or result["run_id"] != block.run_id:
        raise ValueError("Computer-use result belongs to another Job or run")
    answer = block.store.read_bytes(result["answer"])
    audit = block.store.read_bytes(result["audit"])
    public = {**result, "answer": "answer.md", "audit": "computer-use-audit.json"}
    refs = {"result": block.store.commit("result.json", public).to_dict(),
            "answer": result["answer"], "audit": result["audit"]}
    writes = [ArtifactWrite("result", "result.json", block.store.read_bytes(refs["result"]), kind="json"),
              ArtifactWrite("answer", "answer.md", answer, kind="markdown"),
              ArtifactWrite("audit", "computer-use-audit.json", audit, kind="json")]
    if context_memory_section_enabled(block.config.get("source_context") or {}):
        path = "context_sources/outputs/" + hashlib.sha256(block.run_id.encode()).hexdigest() + "/answer.md"
        header = "Run reference: " + block.run_id + "\nTask status: " + result["status"] + "\n\n"
        writes.append(ArtifactWrite("conversation-answer", path, header.encode() + answer, kind="markdown"))
    publication = publish_files(block, writes, name="computer-use-results")
    report_activity("Computer-use result published: " + result["status"], kind="result",
                    step_id=block.step_id, run_dir=block.store.run_dir)
    Conversation(block).notice("result", "The task is complete. Review the observed result in answer.md."
        if result["status"] == "completed" else
        "I stopped before completing the task. Review answer.md and check the desktop before starting again.")
    return {"status": result["status"], "artifacts": refs, "published_files": publication}
