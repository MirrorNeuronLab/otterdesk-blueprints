"""Public action summaries for the investigation monitor, without evidence bodies."""

import json
import time
from mn_sdk.agent_events import emit_agent_event


def observe_action(action, state, execute):
    args = action.get("arguments", {})
    operation = str(args.get("operation", action["name"]))[:100]
    skill = str(args.get("skill", ""))[:200]
    tool_args = args.get("arguments", {})
    tool_args = tool_args if isinstance(tool_args, dict) else {}
    query = (
        tool_args.get("rgql")
        or tool_args.get("query")
        or tool_args.get("evidence_id")
        or ""
    )
    query = str(query or args.get("question") or tool_args.get("source_id") or "")
    label = f"{skill} {operation}".strip()
    display = " ".join(query[:1000].split()) or label
    fields = {
        "action_id": len(state["records"]),
        "action": str(action["name"])[:100],
        "skill": skill,
        "operation": operation,
        "query": query[:1000],
        "query_truncated": len(query) > 1000,
        "parameters_preview": json.dumps(
            tool_args.get("params", {}), ensure_ascii=False
        )[:500],
        "reason": str(action.get("reason", ""))[:300],
        "audit": "case/agent_checkpoint.json",
    }
    started = time.monotonic()
    emit_agent_event(
        "investigation_action_started",
        {**fields, "message": f"Requested {operation}: {display}"},
    )
    try:
        result = execute(action, state)
    except Exception as exc:
        emit_agent_event(
            "investigation_action_failed",
            {
                **fields,
                "message": f"Failed {operation}: {str(exc)[:300]} — {display}",
                "error_type": type(exc).__name__,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        raise
    graph = (
        result.get("provenance") == "observed_graph_query"
        if isinstance(result, dict)
        else False
    )
    summary = {}
    if isinstance(result, dict) and result.get("reused"):
        emit_agent_event(
            "investigation_action_reused",
            {**fields, "message": f"Reused prior result: {display}"},
        )
        return result
    if graph:
        rows = result.get("result", {}).get("rows", [])
        summary = {"engine": "MN Graph Engine (Rust)", "row_count": len(rows)}
    emit_agent_event(
        "investigation_action_completed",
        {
            **fields,
            **summary,
            "message": f"{'Rust graph' if graph else operation} completed: {display}"
            + (f" ({summary['row_count']} rows)" if graph else ""),
            "duration_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return result
