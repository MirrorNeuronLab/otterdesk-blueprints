"""Test fixtures drive native hooks through the real stock SDK worker."""

from functools import lru_cache
import os
from pathlib import Path
from unittest.mock import patch

from mn_blueprint_blocks.context import BlockContext
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore


def block_context(context):
    from mn_sdk.run_retry import effective_configuration, retry_context

    return BlockContext(
        store=CommittedJsonStore(context["run_dir"]),
        invocation_id="domain-fixture",
        revision="domain-fixture@1",
        original_config=context.get("config", {}),
        config=effective_configuration(context.get("config", {}), retry_context()),
        job_id=context.get("job_id") or "",
        job_data_dir=str(context.get("job_data_dir") or ""),
        run_id=str(
            context.get("run_id")
            or os.environ.get("MN_WORKFLOW_RUN_ID")
            or Path(context["run_dir"]).name
        ),
    )


def initialization_inputs(context):
    from domain.state import freeze_files, save_state

    block = block_context(context)
    if "_native_structure" not in context:
        root = block.store.run_dir
        names = [
            "snapshot.json",
            *[
                str(path.relative_to(root))
                for path in (root / "evidence/snapshots").rglob("*")
                if path.is_file()
            ],
        ]
        capture = save_state(
            block,
            "capture",
            inputs=context.get("payload") or {},
            files=freeze_files(block, names),
        )
        names = [
            str(path.relative_to(root))
            for path in (root / "analysis").glob("*")
            if path.is_file()
        ]
        names += [
            str(path.relative_to(root))
            for path in (root / "data").glob("*.json")
            if path.is_file()
        ]
        state = save_state(
            block,
            "structure",
            inputs=context.get("payload") or {},
            files=freeze_files(block, names),
            capture=capture,
        )
        context["_native_structure"] = block.store.commit(
            "fixture/structure.json", {"evidence": state}
        ).to_dict()
    return {
        **(context.get("payload") or {}),
        "previous": {"result": context["_native_structure"]},
    }


@lru_cache
def instances():
    from mn_sdk.blueprints import compile_blueprint, read_blueprint

    root = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    return compile_blueprint(read_blueprint(root)).manifest["metadata"][
        "mn_blocks_lock"
    ]


def invoke(context, step, inputs, *, phase="execute", identity=None, llm_client=None):
    from mn_sdk.run_retry import retry_context

    block = block_context(context)
    lock = instances()
    env = {
        **os.environ,
        "MN_RUN_DIR": str(block.store.run_dir),
        "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
    }
    if context.get("output_folder"):
        env["MN_JOB_OUTPUT_DIR"] = str(context["output_folder"])
    with patch.dict(os.environ, env):
        result = run(
            StepContext(
                step_id=step,
                job_id=block.job_id,
                job_data_dir=block.job_data_dir,
                run_id=block.run_id,
                idempotency_key=identity or step,
                config=context["config"],
                environment=env,
                retry=retry_context(env),
                message={"_mn_step": {"step_input": inputs}},
            ),
            instance=lock["steps"][step],
            revision=lock["revision"],
            phase=phase,
            resources={"llm": llm_client} if llm_client else {},
        )
        context["_native_last_output"] = result.outputs
        return result


def initializer(context, *, llm_client=None):
    result = invoke(
        context,
        "investigate_architecture",
        initialization_inputs(context),
        llm_client=llm_client,
    )
    value = CommittedJsonStore(context["run_dir"]).read(result.outputs["result"])
    return value, result.artifacts


def planner(context, work):
    from domain.catalog_store import fingerprint

    store = CommittedJsonStore(context["run_dir"])
    # This is the same artifact-valued seed port Core gives a real child planner.
    seed = store.commit(
        "fixture/seeds/" + fingerprint(work["context"]) + ".json",
        {"context": work["context"]},
    )
    revision = work["_child"]["revision"]
    value = invoke(
        context,
        "investigate_architecture",
        {"seed": seed.to_dict(), "_child": {**work["_child"], "round": revision}},
        phase="plan",
        identity=f"plan-{revision}",
    ).outputs
    if value["child_plan"]["decision"] == "stop":
        context["_native_terminal"] = value["child_plan"]["output"]["result"]
    return value


def publish(context):
    from domain.catalog_planning import summarize
    from domain.catalog_store import CatalogStore

    block = block_context(context)
    if "_native_terminal" not in context:
        store = CatalogStore(block.store.run_dir)
        path = next(
            path
            for path in sorted(
                store.path("catalog/plans").glob("decision-*.json"), reverse=True
            )
            if store.read(str(path.relative_to(store.root)))["plan"]["done"]
        )
        decision = store.read(str(path.relative_to(store.root)))
        revision = int(path.stem.removeprefix("decision-"))
        summary = summarize(
            block,
            {
                "input": {
                    "seed": {"context": decision["context"]},
                    "_child": {"revision": revision},
                }
            },
        )
        context["_native_terminal"] = block.store.commit(
            "fixture/terminal.json", summary
        ).to_dict()
    result = invoke(
        context,
        "publish_architecture_review",
        {"previous": {"result": context["_native_terminal"]}},
    )
    return block.store.read(result.outputs["result"]), result.artifacts


def review_work(context, work, *, llm_client):
    from domain.catalog_store import CatalogStore
    from domain.catalog_planning import catalog_settings
    from domain.review_admission import admit
    from handoff_test_support import review_task

    block = block_context(context)
    store = CatalogStore(block.store.run_dir)
    saved = store.load_ref(work["context"])
    plan = store.load_ref(saved["plan"])
    task = store.load_ref(work["task"])
    review, opener = catalog_settings(block.original_config)
    reference = admit(store, saved, plan, task, review, opener, run_id=block.run_id)
    assert reference is not None
    review_task(
        context,
        work["context"],
        {
            "id": task["task_id"],
            "context": work["context"],
            "task": work["task"],
            "review_input": reference,
        },
        llm_client,
    )
    return store.result(task["task_id"])
