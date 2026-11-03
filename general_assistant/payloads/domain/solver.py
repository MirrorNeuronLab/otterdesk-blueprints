"""Fence a single Mac task; interrupted desktop work is never replayed."""
from mn_sdk.agent_events import report_activity

from .configuration import read_value, settings


def solve(block, inputs):
    block.check()
    settings(block)
    admitted = read_value(block, inputs["previous"])
    request = read_value(block, admitted["request"])["data"]
    if request["job_id"] != block.job_id or request["run_id"] != block.run_id:
        raise ValueError("Computer-use admission belongs to a different Job or run")

    def execute():
        marker = block.root + "/private/desktop-started.json"
        if block.store.path(marker).exists():
            raise RuntimeError("An interrupted computer-use task requires reconciliation before another run; do not repeat desktop actions")
        block.store.commit(marker, {"request_id": request["request_id"]}, kind="computer_session_fence")
        from .engine import run
        report_activity("Starting the requested task in the mn computer use app", kind="action",
                        step_id=block.step_id, run_dir=block.store.run_dir)
        result = run(block, request)
        answer = block.store.commit_bytes("answer.md", result.pop("answer").encode(), kind="markdown")
        audit = block.store.commit("computer-use-audit.json", result.pop("audit"), kind="computer_use_audit")
        return {"schema_version": "otterdesk.computer_use.result.v1", **result,
                "job_id": block.job_id, "run_id": block.run_id, "request_id": request["request_id"],
                "supervisor_instruction_revision": request["supervisor_instruction_revision"],
                "answer": answer.to_dict(), "audit": audit.to_dict()}

    return {"outcome": block.freeze_checkpoint(block.root + "/solved.json", execute).to_dict()}
