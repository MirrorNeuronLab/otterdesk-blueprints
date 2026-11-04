"""Live domain supervision; SDK owns public Job controls and operation envelopes."""

import asyncio
import time
from typing import Literal


def create_operator_mcp_server(operator, *, server_factory=None):
    from mcp.server.mcpserver import Context
    from mcp.types import InputRequiredResult
    from mn_sdk_mcp import (create_mrtr_mcp_server, domain_tool, job_activity_input_required,
                            resolve_job_activity_receipt)
    globals().update(Context=Context, InputRequiredResult=InputRequiredResult)
    port = operator.mcp_socket.getsockname()[1] if hasattr(operator, "mcp_socket") else 62009
    server = create_mrtr_mcp_server("CCTV co-worker", host="127.0.0.1", port=port,
                                    instructions="Use completed NVIDIA video window observations. A read never starts capture. "
                                                 "A goal change affects future windows; it does not confirm a condition.",
                                    server_factory=server_factory)

    @domain_tool(server, name="get_operator_status", structured_output=True)
    def get_operator_status(question: str = "") -> dict:
        snapshot = operator.snapshot()
        session = snapshot["session"]
        latest = snapshot["captions"][-1] if snapshot["captions"] else None
        return {"ready": snapshot["phase"] == "running" and session["status"] == "running", "connected": snapshot["preview"]["connected"],
                "status": session["status"], "state": session["status"],
                "summary": (snapshot["error"] or (latest["content"] if latest else "No completed video observations yet.")),
                "instruction": session.get("instruction"), "instruction_revision": session.get("instruction_revision", 0),
                "observed_at": latest["end_time"] if latest else None,
                "understanding": latest, "pipeline": {"analysis": session, "preview": snapshot["preview"]},
                "warning": snapshot["limitation"]}

    @domain_tool(server, name="get_operator_activity", structured_output=True)
    def get_operator_activity(after_revision: int = 0) -> dict:
        if isinstance(after_revision, bool) or after_revision < 0:
            raise ValueError("after_revision must be a non-negative integer.")
        return operator.exchange.updates(after_revision=after_revision, kinds=["result"], include_staged=False, limit=20)

    @domain_tool(server, name="get_video_history", structured_output=True)
    def get_video_history(after: str = "", before: str = "") -> dict:
        result = operator.store.history(after=after, before=before, limit=12)
        return {**result, "summary": ("Saved sampled video observations." if result["observations"] else "No saved observations match this interval."),
                "state": "completed", "limitation": "Bounded video captions, not an exhaustive event record or unique-person count."}

    @domain_tool(server, name="get_pipeline_benchmarks", structured_output=True)
    def get_pipeline_benchmarks() -> dict:
        observations = operator.store.history(current_run=True)["observations"]
        def timing(field):
            values = sorted(item[field] for item in observations if item.get(field) is not None)
            return {"samples": len(values), "p50_ms": values[(len(values) - 1) // 2] if values else None,
                    "p95_ms": values[min(len(values) - 1, int(len(values) * .95))] if values else None}
        return {"state": "completed", "summary": "NVIDIA-reported retained window timings; camera startup and model loading are excluded.",
                "vlm_inference": timing("vlm_latency_ms"), "video_window": timing("chunk_latency_ms")}

    @domain_tool(server, name="set_monitoring_instruction", structured_output=True)
    async def set_monitoring_instruction(command_id: str, instruction: str = "", clear: bool = False,
                                         analyze_now: bool = True) -> dict:
        return await operator.analysis.change_goal(command_id, instruction, clear)

    @domain_tool(server, name="get_operation_status", structured_output=True)
    def get_operation_status(operation_id: str, kind: Literal["command"] = "command") -> dict:
        result = operator.store.command(operation_id)
        if result is None:
            raise ValueError("No monitoring change has this request ID.")
        return result

    @domain_tool(server, name="watch_job_activity", structured_output=True)
    async def watch_job_activity(after_event_id: str = "", wait_seconds: float = 20,
                                 ctx: Context = None) -> dict | InputRequiredResult:
        if ctx is not None:
            receipt = resolve_job_activity_receipt(ctx)
            if receipt is not None:
                return receipt
        deadline = time.monotonic() + min(max(wait_seconds, 0), 25)
        while True:
            previous = operator.exchange.get_record("result", after_event_id, include_staged=False) if after_event_id else None
            if previous:
                updates = operator.exchange.updates(after_revision=previous["revision"], kinds=["result"], include_staged=False, limit=1)["updates"]
                latest = updates[0] if updates else None
            else:
                latest = operator.exchange.latest_record("result", include_staged=False)
            if latest:
                return job_activity_input_required(latest["payload"], after_event_id=after_event_id)
            if time.monotonic() >= deadline:
                return {"schema_version": "mn.mcp.job_activity_watch.v1", "delivered": False,
                        "cursor": after_event_id, "activity": None}
            await asyncio.sleep(min(.5, max(0, deadline - time.monotonic())))

    return server
