"""Supervised lifecycle with bounded retry delays and redacted status artifacts."""
import json
import time
from pathlib import Path
from mn_prototype_supervised_service_agent import ServiceContext, SupervisedServiceSpec, create_agent
from mn_sdk.step_runtime import StepContext, receive_input
from mn_sdk.blueprint_support import source_manifest, write_json
from .runtime_services import runtime_context_for_step
from .collaboration import stable_identity


def run_service(context=None, **options):
    step = context or StepContext.from_environment()
    keys = frozenset(source_manifest(__file__)["contracts"]["inputs"])
    incoming = receive_input(step, required_keys=keys).payload
    runtime = runtime_context_for_step(inputs={k:v for k,v in incoming.items() if k in keys}, config=step.config)
    runtime["stable_job_id"] = stable_identity(runtime)
    if not runtime.get("job_data_dir"):
        raise ValueError("A durable Job data directory is required")
    from .cycle import cycle
    service = ServiceContext(config=runtime, run_dir=runtime["run_dir"])
    failures = 0
    def tick(ctx):
        nonlocal failures
        try:
            result = cycle(runtime, ctx.stop_event)
            failures = 0
        except Exception as exc:
            failures += 1
            result = {"status":"needs_review", "error_type":type(exc).__name__, "message":"Marketing work could not continue. Review configuration and try again."}
            # No exception text: transport/model failures may include private data.
            ctx.stop_event.wait(min(900, 15 * 2 ** min(failures, 6)))
        write_json(Path(runtime["run_dir"]) / "marketing_status.json", {"schema_version":"mn.gtm.status.v1", **result, "updated_at":time.time()})
    config = runtime["config"].get("service", {})
    return create_agent(SupervisedServiceSpec(cycle=tick, interval_seconds=max(60, float(config.get("poll_seconds",60))),
        max_cycles=config.get("max_cycles")))(context=service)
