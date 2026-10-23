"""Admit a task and an immutable workspace/memory snapshot for OpenShell."""
from pathlib import Path

from mn_blueprint_blocks.contracts import fingerprint
from mn_opencode_skill import OpenCodeGateway
from mn_sdk.agent_events import report_activity
from mn_sdk.integrations.block_inputs import declared_inputs, save_declared_inputs

from .configuration import settings
from .conversation import Conversation
from .memory import load

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".aws", ".ssh"}


def prepare(block, inputs):
    block.check()
    limits = settings(block)
    checkpoint = block.root + "/task/request.json"

    def admit():
        values = declared_inputs(block, inputs, runtime_file=__file__)
        folder = values.get("input_folder")
        if not isinstance(folder, str) or not folder.strip():
            raise ValueError("Choose an input folder before starting work")
        task = values.get("task")
        if task is None:
            task = Conversation(block).ask("task", "What would you like me to do with the input folder?")
        if not isinstance(task, str) or not task.strip() or len(task.encode()) > 64000:
            raise ValueError("task must contain 1..64000 UTF-8 bytes")
        save_declared_inputs(block, {**values, "task": task.strip()}, runtime_file=__file__)
        attachments, total = {}, 0
        if folder:
            root = Path(folder).resolve(strict=True)
            if not root.is_dir():
                raise ValueError("input_folder must be a staged directory")
            for path in sorted(root.rglob("*")):
                block.check()
                rel = path.relative_to(root)
                if EXCLUDED.intersection(rel.parts) or path.name == ".env" or path.name.startswith(".env."):
                    continue
                if path.is_symlink():
                    raise ValueError("Supporting workspaces cannot contain symlinks")
                if not path.is_file():
                    continue
                total += path.stat().st_size
                if len(attachments) >= limits["max_input_files"] or total > limits["max_input_bytes"]:
                    raise ValueError("Supporting workspace exceeds the input quota")
                reference = block.store.commit_bytes("admitted/input/" + rel.as_posix(), path.read_bytes())
                attachments[rel.as_posix()] = reference.to_dict()
        host = limits["gateway_host"]
        gateway = {"api_base": f"http://{host}:{limits['gateway_port']}/v1", "model": "default"}
        OpenCodeGateway(**gateway).provider("mn/default")
        request = {
            "task": task.strip(), "settings": limits, "gateway": gateway,
            "job_id": block.job_id, "run_id": block.run_id,
            "request_id": fingerprint([block.job_id, block.run_id, block.invocation_id]),
            "memory": load(block, limits), "attachments": attachments,
        }
        report_activity("Prepared the task and private Harness2 context", kind="action",
                        step_id=block.step_id, run_dir=block.store.run_dir)
        return request

    reference = block.freeze_checkpoint(checkpoint, admit)
    # The common checkpoint carries nested immutable attachment references.
    return {"request": reference.to_dict()}
