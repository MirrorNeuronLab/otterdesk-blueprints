"""One bounded black-box invocation with immutable inputs and committed outputs."""
from mn_sdk.agent_events import report_activity
from mn_sdk.artifact_handoff import relative_path

from .configuration import core_connection, read_value, require_openshell


def solve(block, inputs):
    block.check()
    require_openshell()
    admitted = read_value(block, inputs["previous"])
    checkpoint = read_value(block, admitted["request"])
    request = checkpoint["data"]
    if request["job_id"] != block.job_id or request["run_id"] != block.run_id:
        raise ValueError("Harness2 admission belongs to a different Job or run")
    from .engine import run
    report_activity("Solving the task and probing refinements inside OpenShell", kind="action",
                    step_id=block.step_id, run_dir=block.store.run_dir)

    def execute():
        root = block.store.run_dir / "harness-work"
        if root.exists():
            raise RuntimeError("An interrupted Harness2 invocation requires reconciliation")
        root.mkdir()
        with core_connection(request["settings"]):
            outcome = run(block, request, root)
        deliverables, total = {}, 0
        answer = "Harness2 did not produce a complete result. Inspect harness-audit.json for observed failures.\n"
        if outcome["success"]:
            workspace = outcome["chosen"] / "workspace"
            answer = (workspace / "output/answer.md").read_text(encoding="utf-8")
            candidates = [(p, p.relative_to(workspace / "output").as_posix())
                          for p in (workspace / "output").rglob("*") if p.is_file()]
            for path, name in sorted(candidates, key=lambda item: item[1]):
                block.check()
                relative_path(name)
                if path.is_symlink() or name in deliverables:
                    raise ValueError("Invalid or conflicting deliverable path")
                total += path.stat().st_size
                if (len(deliverables) >= request["settings"]["max_output_files"]
                        or total > request["settings"]["max_output_bytes"]):
                    raise ValueError("Harness2 deliverables exceed the output quota")
                reference = block.store.commit_bytes("deliverables/" + name, path.read_bytes())
                deliverables[name] = reference.to_dict()
        answer_ref = block.store.commit_bytes("answer.md", answer.encode(), kind="markdown")
        memory_ref = block.store.commit("private/harness-memory.json", outcome["memory"], kind="harness_memory")
        audit_ref = block.store.commit("harness-audit.json", outcome["audit"], kind="harness_audit")
        result = {"schema_version": "otterdesk.general_assistant.result.v1",
                  "status": "completed" if outcome["success"] else "failed",
                  "job_id": block.job_id, "run_id": block.run_id,
                  "request_id": request["request_id"], "answer": answer_ref.to_dict(),
                  "supervisor_instruction_revision": request.get("supervisor_instruction_revision"),
                  "deliverables": deliverables, "improvement": audit_ref.to_dict(),
                  "memory": memory_ref.to_dict(), "expected_generation": request["memory"]["generation"]}
        return result

    reference = block.freeze_checkpoint(block.root + "/solved.json", execute)
    return {"outcome": reference.to_dict()}
