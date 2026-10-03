"""Source-linked VC runtime facts; external RAG passages never enter this store."""

import json
from pathlib import Path

from mn_sdk.blueprint_support import WorkflowStateStore
from mn_sdk.context_session.contracts import digest


def runtime_observations(ctx):
    store = ctx.get("state_store") or WorkflowStateStore(ctx["run_dir"])
    for company, evidence in store.list_entity_objects("company_evidence").items():
        source_map = {s["source_id"]: s for s in evidence.get("source_records", [])}
        evidence_map = {e["evidence_id"]: e for e in evidence.get("evidence_items", [])}
        for claim in evidence.get("claim_records", []):
            supports = [evidence_map[id] for id in claim.get("evidence_ids", []) if id in evidence_map]
            sources = [source_map[e["source_id"]] for e in supports if e.get("source_id") in source_map]
            # Normalized runtime claims, qualification and references, not document
            # excerpts or external reference-knowledge chunks.
            record = {"company": company, "kind": "claim", "observation_id": claim["claim_id"],
                      "claim": claim.get("canonical_claim"), "value": claim.get("value"),
                      "unit": claim.get("unit"), "claim_type": claim.get("claim_type"),
                      "claim_family": str(claim.get("claim_type") or "").split(".")[0],
                      "qualification": claim.get("verification_status", "unverified"),
                      "required_next_evidence": claim.get("required_next_evidence", []),
                      "evidence_ids": claim.get("evidence_ids", []),
                      "source_ids": [s["source_id"] for s in sources],
                      "source_types": [s.get("source_type") for s in sources],
                      "timestamp": max((s.get("retrieved_at") or "" for s in sources), default="")}
            record["relations"] = [{"source": company, "relation": "HAS_CLAIM", "target": claim["claim_id"]}]
            record["relations"] += [{"source": claim["claim_id"], "relation": "SUPPORTED_BY", "target": id}
                                    for id in record["source_ids"]]
            yield record
        for source in source_map.values():
            yield {"company": company, "kind": "source", "observation_id": source["source_id"],
                   "title": source.get("title"), "source_type": source.get("source_type"),
                   "status": source.get("retrieval_status"), "quality": source.get("source_quality_score"),
                   "qualification": source.get("source_quality_label", "unverified"),
                   "timestamp": source.get("retrieved_at") or ""}
    for company, analysis in store.list_entity_objects("analyses").items():
        for method_id, method in analysis.get("methods", {}).items():
            yield {"company": company, "kind": "method", "observation_id": company + ":" + method_id,
                   "method_id": method_id, "status": method.get("status"), "score": method.get("score"),
                   "missing_evidence": method.get("missing_evidence", []),
                   "assumptions": method.get("assumptions", []), "warnings": method.get("warnings", []),
                   "evidence_refs": method.get("evidence_refs", []),
                   "qualification": "runtime_method_result", "timestamp": analysis.get("generated_at") or ""}
    trace = Path(ctx["run_dir"]) / "llm_rag_trace.jsonl"
    if trace.is_file():
        for line in trace.read_text().splitlines():
            event = json.loads(line)
            payload = event.get("payload", {})
            if (event.get("type") not in ("observability_operation_completed", "observability_operation_failed")
                    or payload.get("phase") not in ("public_tool_call", "agentic_research")):
                continue
            agent = payload.get("agent_id") or payload.get("verification_target")
            if not agent:
                continue
            # Only runtime execution metadata; no RAG body or model prompt.
            yield {"company": payload.get("company") or "", "kind": "tool", "agent_id": agent,
                   "observation_id": payload["operation_id"], "timestamp": event["timestamp"],
                   "operation": payload.get("operation"), "status": payload.get("status"),
                   "tool_status": payload.get("tool_status"), "error": payload.get("error"),
                   "source_count": payload.get("source_count"), "stop_reason": payload.get("stop_reason"),
                   "qualification": "recorded_tool_outcome_not_external_confirmation"}


def ingest_runtime_observations(memory, ctx):
    receipts = []
    records = list(runtime_observations(ctx))
    snapshot_id = digest(records)
    for record in records:
        record.update(memory_family="vc_runtime", snapshot_id=snapshot_id)
        text = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        receipt = memory.observe(text, event_id=["vc-runtime-fact", digest(record)],
            allow=["vc-actor-review"], upstream=[{"artifact": "workflow_state", "company": record["company"],
                                                "observation_id": record["observation_id"]}])
        receipts.append({**receipt, "runtime_kind": record["kind"]})
    return receipts, snapshot_id
