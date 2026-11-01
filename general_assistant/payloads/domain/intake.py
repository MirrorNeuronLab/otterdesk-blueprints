"""Freeze the user's Mac task and explicit working rules."""
import json

from jsonschema import validate
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.agent_events import report_activity
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.integrations.block_inputs import declared_inputs, save_declared_inputs

from .configuration import settings
from .conversation import Conversation


def prepare(block, inputs):
    block.check()
    limits = settings(block)

    def admit():
        values = declared_inputs(block, inputs, runtime_file=__file__)
        instructions = values.get("supervisor_instructions", [])
        declaration = source_manifest(__file__)["contracts"]["inputs"]["supervisor_instructions"]
        validate(instructions, {key: value for key, value in declaration.items() if key != "required"})
        if (len(json.dumps(instructions, ensure_ascii=False, separators=(",", ":")).encode()) > 16000
                or len({item["id"] for item in instructions}) != len(instructions)):
            raise ValueError("Saved task instructions exceed the supported bounds")
        task = values.get("task")
        target_app = values.get("target_app_bundle_id")
        if target_app is None:
            target_app = ""
        app_declaration = source_manifest(__file__)["contracts"]["inputs"]["target_app_bundle_id"]
        validate(target_app, {key: value for key, value in app_declaration.items() if key != "required"})
        if task is None or isinstance(task, str) and not task.strip():
            task = Conversation(block).ask("task", "What would you like me to do on this Mac?")
        if not isinstance(task, str) or not task.strip() or len(task.encode()) > 64000:
            raise ValueError("task must contain 1..64000 UTF-8 bytes")
        save_declared_inputs(block, {**values, "task": task.strip(), "target_app_bundle_id": target_app}, runtime_file=__file__)
        report_activity("Prepared the Mac task and saved working rules", kind="action",
                        step_id=block.step_id, run_dir=block.store.run_dir)
        return {"task": task.strip(), "target_app_bundle_id": target_app, "settings": limits,
                "supervisor_instructions": instructions,
                "supervisor_instruction_revision": fingerprint(instructions),
                "job_id": block.job_id, "run_id": block.run_id,
                "admitted_at": block.wall_time(),
                "request_id": fingerprint([block.job_id, block.run_id, block.invocation_id])}

    return {"request": block.freeze_checkpoint(block.root + "/task/request.json", admit).to_dict()}
