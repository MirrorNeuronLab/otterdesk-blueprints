"""Supervised lifecycle with bounded retry delays and redacted status artifacts."""
import time
from mn_prototype_supervised_service_agent import ServiceContext, SupervisedServiceSpec, create_agent
from mn_sdk.blueprint.steps import StepContext, receive_input
from mn_sdk.blueprint.context import source_manifest
from .runtime_services import runtime_context_for_step
from mn_sdk.blueprint.services import current_job_id, service_status_publisher


def run_service(context=None, **options):
    step = context or StepContext.from_environment()
    keys = frozenset(source_manifest(__file__)["contracts"]["inputs"])
    incoming = receive_input(step, required_keys=keys).payload
    runtime = runtime_context_for_step(inputs={k:v for k,v in incoming.items() if k in keys}, config=step.config)
    runtime["stable_job_id"] = current_job_id()
    if not runtime.get("job_data_dir"):
        raise ValueError("A durable Job data directory is required")
    from .cycle import cycle
    service = ServiceContext(config=runtime, run_dir=runtime["run_dir"])
    publish_status = service_status_publisher(runtime)
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
        publish_status({**result, "updated_at": time.time()})
    config = runtime["config"].get("service", {})
    return create_agent(SupervisedServiceSpec(cycle=tick, interval_seconds=max(60, float(config.get("poll_seconds",60))),
        max_cycles=config.get("max_cycles")))(context=service)
