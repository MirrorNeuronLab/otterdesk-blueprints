"""Compiled report-worker fixture; no shell entrypoint or production adapter."""

import json
from pathlib import Path
import sys

from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_publication_files import deliver_files
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


class NativeReport:
    def __init__(self, directory, *, derive=False):
        self.directory, self.count = directory, 0
        sys.path.insert(0, str(ROOT / "payloads"))
        package = read_blueprint(ROOT)
        config = resolve_config(package)
        compiled = compile_blueprint(package, config).manifest
        node = next(row for row in compiled["agents"]["nodes"] if row["node_id"] == "report_writer")
        assert node["config"]["command"] == ["python3", "-m", "mn_sdk.step_runtime"]
        self.options = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
        descriptor = directory / "runtime.json"
        descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, config)))
        self.state_file = directory / "core-state.json"
        self.state_file.write_text("{}")
        self.run_id = "runtime-run" if derive else "report-run"
        root = directory / "runs" / self.run_id if derive else directory / "run"
        self.store = CommittedJsonStore(root)
        environment = {"MN_CONTEXT_FILE": str(self.state_file), "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
            "MN_BLOCK_EVENT_PROTOCOL": "mn.block_events/v1", "MN_BLOCK_EVENT_PUBLICATION_PROTOCOL": "mn.published_files/v1",
            "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
        environment.update({"MN_RUNS_ROOT": str(directory / "runs")} if derive else {"MN_RUN_DIR": str(root)})
        self.environment, self.config = environment, config.data

    def execute(self, state, events):
        self.count += 1
        observation = self.store.commit(f"input-{self.count}.json", {"schema": "otterdesk.cctv.observation.v1",
            "scope": {"job_id": "report-job", "run_id": self.run_id}, "state": state, "events": events}, kind="cctv_observation")
        context = StepContext(step_id="write_cctv_report", agent_id="report_writer", job_id="report-job", run_id=self.run_id,
            config=self.config, environment=self.environment,
            message={"envelope": {"message_id": "report-" + str(self.count)}, "body": {"observation": observation.to_dict()}})
        result = run(context, **self.options)
        # Simulate accepted owner copy; Core acceptance/handoff is independently
        # verified by ExUnit and native tests assert zero worker-side copying.
        deliver_files(BlockContext(store=self.store, invocation_id="owner-copy", revision="test",
            environment={}, agent_id="report_writer"), result.publication)
        self.state_file.write_text(json.dumps({"agent_state": {"version": "mn.block_event_state/v1", "reference": result.event_result["next"]}}))
        return result
