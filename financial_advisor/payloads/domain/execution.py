"""Route-neutral specialist execution and durable run preparation."""

from __future__ import annotations

import time

from .common import *
from .review_services import accumulate_llm_usage, build_llm_client, live_llm_requested, llm_usage, step_model_profile, usage_delta
from .runtime_services import build_context
from .state import load_state, persist_runtime_context, read_json, runtime_context_path, save_state, write_failed_run

def step_result(ctx: dict[str, Any], step_id: str, output: dict[str, Any], **metadata: Any) -> dict[str, Any]:
    result = {
        "schema": "mn.agent.result.v1",
        "run_id": ctx["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "agent_id": step_id,
        "runtime_step_mode": "agent_handler",
        "blueprint": BLUEPRINT_ID,
        "status": "completed",
        "message_type": OUTPUT_MESSAGE_BY_AGENT[step_id],
        "summary": f"{step_id.replace('_', ' ').title()} completed.",
        "run": {
            "run_id": ctx["run_id"],
            "status": "completed",
            "ended_at": utc_now_iso(),
        },
        "outputs": output,
        **metadata,
    }
    write_json(ctx["run_dir"] / f"{step_id}_result.json", result)
    write_json(ctx["run_dir"] / "workflow_state" / f"{step_id}_result.json", result)
    return result

def ensure_run_started(ctx: dict[str, Any]) -> None:
    run_path = ctx["run_dir"] / "run.json"
    if not run_path.exists():
        write_json(ctx["run_dir"] / "config.json", ctx["config"])
        write_json(
            ctx["run_dir"] / "inputs.json",
            {
                "payload": ctx["payload"],
                "document_folder": str(ctx["document_folder"]),
                "output_folder": str(ctx["output_folder"]),
            },
        )
        write_json(
            run_path,
            {
                "run_id": ctx["run_id"],
                "blueprint_id": BLUEPRINT_ID,
                "status": "running",
                "started_at": ctx["started_at"],
            },
        )
        append_event(ctx["run_dir"], "blueprint_status", {"status": "running", "component": BLUEPRINT_ID})
    persist_runtime_context(ctx)

def finish_completed_run(ctx: dict[str, Any], final_output: dict[str, Any]) -> dict[str, Any]:
    final_artifact = final_output["final_artifact"]
    output_files = list(final_output.get("output_files") or [])

    for name in ("action_ledger.json", "artifact_quality.json", "run_health.json"):
        source_path = ctx["output_folder"] / name
        if source_path.exists():
            write_json(ctx["run_dir"] / name, read_json(source_path))

    final_artifact_path = ctx["output_folder"] / "final_artifact.json"
    result_path = ctx["output_folder"] / "result.json"
    for path in (final_artifact_path, result_path):
        path_text = str(path)
        if path_text not in output_files:
            output_files.append(path_text)
    final_artifact["output_files"] = output_files

    result = {
        "run_id": ctx["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "final_artifact": final_artifact,
        "output_files": output_files,
    }
    write_json(final_artifact_path, final_artifact)
    write_json(result_path, result)
    write_json(ctx["run_dir"] / "result.json", result)
    write_json(ctx["run_dir"] / "final_artifact.json", final_artifact)
    write_json(
        ctx["run_dir"] / "run.json",
        {
            "run_id": ctx["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "completed_at": utc_now_iso(),
        },
    )
    for name in ("result.json", "final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json"):
        append_event(ctx["run_dir"], "artifact_written", {"path": str(ctx["output_folder"] / name)})
    append_event(
        ctx["run_dir"],
        "human_input_requested",
        {
            "mode": "approval_required",
            "reason": "Review financial advisor packet before filing, trading, money movement, bill payment, or external sharing.",
        },
    )
    append_event(ctx["run_dir"], "blueprint_status", {"status": "completed", "component": BLUEPRINT_ID})
    return result



def execute_runtime_handler(
    step_id: str,
    handler: Any,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
    config_json: str | None = None,
    finalize_run: bool = False,
) -> dict[str, Any]:
    """Execute one manifest-resolved Financial Advisor handler."""

    step_id = str(step_id or "").strip()
    if not step_id:
        raise ValueError("Financial Advisor workflow step id is required")
    ctx = build_context(
        inputs=inputs,
        config=config,
        config_json=config_json,
        runs_root=runs_root,
        run_id=run_id,
        llm_client=llm_client,
    )
    step_started = time.monotonic()
    ensure_run_started(ctx)
    try:
        append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": step_id})
        profile = step_model_profile(ctx["config"], step_id)
        ctx["state"].setdefault("model_profiles_used", {})[step_id] = {
            "llm_config": profile["llm_config"],
            "model": profile["model"],
            "runtime_model": profile["runtime_model"],
        }
        usage_before = llm_usage(ctx["llm"])
        ctx["step_llm_usage_before"] = usage_before
        output = handler(ctx)
        usage_after = llm_usage(ctx["llm"])
        llm_delta = usage_delta(usage_before, usage_after)
        if llm_delta.get("fallback_calls") and live_llm_requested(ctx["config"], ctx.get("payload")):
            raise RuntimeError(f"Live LLM fallback was used during {step_id}; failing normal run instead of silently degrading.")
        cumulative_llm_usage = accumulate_llm_usage(ctx, llm_delta)
        ctx["state"].setdefault("workflow", {})[step_id] = output
        append_event(
            ctx["run_dir"],
            f"{step_id}_completed",
            {
                "step_id": step_id,
                "runtime_step_mode": "manifest_handler",
                "llm_config": profile["llm_config"],
                "model": profile["model"],
                "llm_usage_delta": llm_delta,
                "llm_usage": cumulative_llm_usage,
            },
        )
        append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": step_id})
        save_state(ctx["run_dir"], ctx["state"])
        final_result: dict[str, Any] | None = None
        if finalize_run:
            final_result = finish_completed_run(ctx, output)
        metadata: dict[str, Any] = {
            "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
            "output_files": final_result.get("output_files", []) if final_result else output.get("output_files", []),
        }
        if final_result:
            metadata["final_artifact"] = final_result["final_artifact"]
        elif isinstance(output.get("final_artifact"), dict):
            write_json(ctx["run_dir"] / "final_artifact.json", output["final_artifact"])
            metadata["final_artifact"] = output["final_artifact"]
        return step_result(ctx, step_id, output, **metadata)
    except Exception as exc:
        append_event(
            ctx["run_dir"],
            "workflow_step_failed",
            {
                "step_id": step_id,
                "runtime_step_mode": "workflow_step_handler",
                "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
                "error": str(exc),
            },
        )
        append_event(ctx["run_dir"], "blueprint_phase_failed", {"phase": step_id, "error": str(exc)})
        write_failed_run(ctx, exc)
        raise

def final_artifact_for_transport(final_artifact: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: final_artifact.get(key)
        for key in (
            "type",
            "blueprint_id",
            "run_id",
            "executive_summary",
            "recommended_action",
            "confidence",
            "review_only",
            "review_status",
            "customer_readiness",
            "customer_report",
        )
        if key in final_artifact
    }
    compact["artifact_summary"] = {
        "bank_statement_count": (final_artifact.get("bank_statement_extraction") or {}).get("statement_count"),
        "tax_form_count": (final_artifact.get("tax_form_ocr_capture") or {}).get("tax_form_count"),
        "portfolio_total_value": (final_artifact.get("portfolio_risk_review") or {}).get("total_value"),
        "llm_review_count": len([key for key in ("cash_flow", "tax", "portfolio") if (final_artifact.get("llm_analysis") or {}).get(key)]),
        "output_file_count": len(final_artifact.get("output_files") or []),
        "warning_count": len(final_artifact.get("research_warnings") or []),
    }
    compact["transport"] = {
        "compacted": True,
        "omitted_fields": [
            "evidence",
            "research_sources",
            "bank_statement_extraction",
            "household_finance_summary",
            "tax_review_packet",
            "tax_form_ocr_capture",
            "portfolio_risk_review",
            "llm_analysis",
            "output_files",
        ],
        "reason": "Keep workflow step transport small; full review artifacts remain in the output folder.",
    }
    return compact


FINAL_AGENT_ID = "financial_advice_reporter"


__all__ = ["FINAL_AGENT_ID", "execute_runtime_handler", "final_artifact_for_transport"]
