"""Existing policy fixtures call actual native workers during the migration."""

import json
import inspect
import os
from pathlib import Path

from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / "litigation_analyst"


def block_context(context):
    if isinstance(context, BlockContext):
        return context
    root = Path(context["run_dir"])
    return BlockContext(CommittedJsonStore(root), "policy-fixture", "policy-fixture-v1",
        config=context.get("config", {}), job_id=context.get("job_id") or os.environ.get("MN_JOB_ID", ""),
        run_id=context.get("run_id") or os.environ.get("MN_WORKFLOW_RUN_ID") or os.environ.get("MN_RUN_ID", root.name),
        job_data_dir=str(context.get("job_data_dir") or ""))


def phase(original, step_id):
    def invoke(context, inputs=None, *, llm_client=None):
        if isinstance(context, BlockContext):
            return original(context, inputs)
        package = read_blueprint(ROOT)
        key = json.dumps([package.fingerprint, context["config"]], sort_keys=True)
        cached = context.get("_native_binding")
        if cached is None or cached["key"] != key:
            config = resolve_config(package, context["config"])
            compiled = compile_blueprint(package, config).manifest
            cached = {"key": key, "config": config.data, "manifest": compiled,
                "descriptor": resolved_worker_descriptor(package, compiled, config)}
            context["_native_binding"] = cached
        compiled = cached["manifest"]
        root = Path(context["run_dir"])
        root.mkdir(parents=True, exist_ok=True)
        descriptor = root / "native-fixture-manifest.json"
        descriptor.write_text(json.dumps(cached["descriptor"]))
        env = {**os.environ, "MN_RUN_DIR": str(root), "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
            "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
        ports = dict(context["payload"])
        if context.get("output_folder"):
            ports["output_folder"] = str(context["output_folder"])
        if step_id == "build_case_indexes":
            ports["previous"] = {"result": context["_native_prepare_case_sources"]}
        elif step_id == "investigate_case_evidence":
            ports["previous"] = {"result": context["_native_build_case_indexes"]}
        elif step_id == "write_review_draft":
            ports["previous"] = {"result": context["_native_terminal"]}
        elif step_id == "preserved_autonomous_explorer":
            ports["previous"] = {"result": context["_native_build_case_indexes"]}
        native = block_context(context)
        invocation = StepContext(step_id=step_id, job_id=native.job_id, run_id=native.run_id,
            job_data_dir=native.job_data_dir, config=cached["config"], environment=env,
            idempotency_key=f"{native.run_id}/{step_id}", message={"body": {"step_input": ports}})
        options = {"block_step_id": step_id, "revision": compiled["metadata"]["mn_blocks_lock"]["revision"]}
        if step_id == "preserved_autonomous_explorer":
            options = {"revision": "litigation_analyst@5.0.0", "instance": {"uses": "mn.blocks.domain_operation@1",
                "hooks": {"operation": "domain.research:investigate", "verify": "domain.research:verified"}}}
        result = run(invocation, **options, resources={"llm": llm_client} if llm_client is not None else {})
        context["_native_" + step_id] = result.outputs["result"]
        if step_id == "preserved_autonomous_explorer":
            context["_native_terminal"] = result.outputs["result"]
        return native.store.read(result.outputs["result"]), result.artifacts

    return invoke


def round_worker(original, template=None):
    """Use real stock planner/task bindings; decode replies for policy fixtures."""
    def invoke(context, work, *, llm_client=None):
        if isinstance(context, BlockContext):
            return original(context, work)
        native = block_context(context)
        cached = context["_native_binding"]
        compiled = cached["manifest"]
        descriptor = native.store.path("native-fixture-manifest.json")
        env = {**os.environ, "MN_RUN_DIR": str(native.store.run_dir),
            "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
        if template is None:
            seed = native.store.commit("fixtures/seed-" + work['context']['sha256'] + ".json", {"context": work["context"]})
            ports = {"seed": seed.to_dict(), "_child": {"round": work["_child"]["revision"], **work["_child"]}}
            parameters = {"block_step_id": "investigate_case_evidence", "phase": "plan",
                "revision": compiled["metadata"]["mn_blocks_lock"]["revision"]}
            identity = f"plan/{work['_child']['revision']}/{work['context']['sha256']}"
            step_id = "plan_litigation_round"
        else:
            task = native.store.read(work["task"])
            if set(task) == {"context", "task"}:
                packet = work["task"]
            else:
                packet = native.store.commit("fixtures/work-" + work["task"]["sha256"] + ".json",
                    {"context": work["context"], "task": work["task"]}).to_dict()
            ports = {"task": packet, "_child": work.get("_child", {})}
            parameters = compiled["workflow"]["child_workflows"]["investigate_case_evidence"]["templates"][template]["implementation"]["with"]
            identity = f"{template}/{packet['sha256']}"
            step_id = template
        invocation = StepContext(step_id=step_id, job_id=native.job_id, run_id=native.run_id,
            job_data_dir=native.job_data_dir, config=cached["config"], environment=env,
            idempotency_key=f"{native.run_id}/{identity}", message={"body": {"step_input": ports}})
        output = run(invocation, resources={"llm": llm_client} if llm_client is not None else {}, **parameters)
        if template is not None:
            return native.store.read(output.outputs["result"])
        decision = output.outputs
        if decision["child_plan"]["decision"] == "stop":
            result = native.store.read(decision["child_plan"]["output"]["result"])
            context["_native_terminal"] = output.outputs["child_plan"]["output"]["result"]
            decision = {"child_plan": {**decision["child_plan"], "output": result, "reason": result["stop_reason"]}}
        return decision

    return invoke


def native_helper(original):
    signature = inspect.signature(original)
    def invoke(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        previous = bound.arguments["context"]
        if isinstance(previous, dict):
            for name, value in (("goal", previous.get("payload", {}).get("goal")),
                    ("review_file", previous.get("payload", {}).get("review_file")),
                    ("output_folder", previous.get("output_folder"))):
                if name in signature.parameters:
                    bound.arguments.setdefault(name, value)
        bound.arguments["context"] = block_context(previous)
        return original(*bound.args, **bound.kwargs)
    return invoke
