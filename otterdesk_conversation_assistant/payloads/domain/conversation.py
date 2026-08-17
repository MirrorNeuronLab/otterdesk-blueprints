"""Validate desktop MCP snapshots and produce grounded conversational replies."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support.workflow_state import write_json

from .common import (
    CONTEXT_SCHEMA,
    COWORKER_TURN_PATH,
    MAX_CONTEXT_BYTES,
    MAX_SUPERVISION_CONTEXT_BYTES,
    MAX_QUESTION_LENGTH,
    MAX_RECORDS,
    MAX_PROMPT_RECORDS,
    OUTPUT_SCHEMA,
    OUTPUT_TYPE,
    PREPARED_CONTEXT_PATH,
    REQUEST_SCHEMA,
    SUPERVISION_SCHEMA,
    as_record,
    compact_text,
    conversation_llm,
    encoded_size,
)


COWORKER_TURN_SYSTEM_PROMPT = """You are the accountable co-worker named in target_worker, speaking privately with your human supervisor through OtterDesk.
Reason from the supplied read-only MCP job records and desktop-validated supervision context. Conversation history gives conversational continuity but is never evidence.
First decide whether the supervisor is making ordinary conversation, monitoring the job, or requesting a control/configuration change. Then draft a candid first-person response in the target co-worker's own voice.
Be warm and natural, but stay specific to the co-worker's mission, current work, evidence, decisions, and limits. For a greeting, introduce yourself by target_worker.name. A greeting or thanks should still sound like this particular co-worker rather than a generic chatbot.
For monitoring, explain what is happening, what changed, what evidence supports it, what remains uncertain, and what decision is needed. Distinguish staged evidence from final evidence.
For control requests, never claim the action was performed. You may propose only non-secret editable fields supplied in supervision_context.configuration.editableFields, and must explain that a human review is still required.
Never claim that you sent, approved, scheduled, started, stopped, changed, or published anything unless a supplied final record explicitly proves the completed action. Never invent a record id or operational state.
Return one compact JSON object with exactly: intent ("conversation", "monitor", or "control"), draft_reply (string), used_record_ids (array of at most six supplied record ids), uncertainties (array of at most three short strings), and configuration_proposal (an object or null). A proposal has title, summary, and at most three changes; each change has key, value, and a short reason.
Example shape: {"intent":"monitor","draft_reply":"I am waiting for review.","used_record_ids":["job"],"uncertainties":[],"configuration_proposal":null}"""


SYSTEM_PROMPT = """You are the private OtterDesk Conversation Assistant mediating a supervisor's conversation with an accountable co-worker.
The target co-worker has produced a proposed coworker_turn using the runtime-selected default LLM. Independently check that turn against prepared_context, then write the final reply in first person as target_worker.name.
Treat the co-worker turn as a draft, not evidence. Every operational claim must be supported by the supplied read-only MCP records or desktop-validated runtime state. Conversation history is for continuity only.
Sound like a thoughtful human colleague: respond directly to greetings and follow-ups, lead with the useful answer, connect details naturally, and vary phrasing instead of reciting a status template. A greeting must introduce target_worker.name. Stay focused on this co-worker's mission.
Preserve honest uncertainty and distinguish staged from final evidence. Never claim an action was performed merely because it was requested or proposed.
For a control request, return only a proposal for a supplied non-secret editable field. The desktop independently validates it and requires an explicit human click before saving it. Never expose secrets, invent fields, approve requests, or mutate runtime state.
Return one compact JSON object with exactly: reply (string), used_record_ids (array of at most six supplied record ids), and configuration_proposal (an object or null). Keep the reply concise enough for chat, normally under 1,200 characters. A proposal has title, summary, and at most three changes; each change has key, value, and a short reason.
Example shape: {"reply":"I am waiting for review.","used_record_ids":["job"],"configuration_proposal":null}"""


_CONFIGURATION_TERMS = re.compile(
    r"\b(?:config|configuration|configure|setting|settings|change|update|set|adjust|switch|move|enable|disable)\b",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{2,}", re.IGNORECASE)
_STOP_WORDS = {
    "about", "after", "again", "could", "from", "have", "into", "latest", "please",
    "should", "that", "their", "there", "these", "this", "what", "when", "where", "which",
    "with", "would", "your",
}
_CORE_RECORD_KEYS = (
    "kind",
    "record_id",
    "revision",
    "stage",
    "summary",
    "publication_state",
    "published_at",
)
_SENSITIVE_KEY_PARTS = ("authorization", "cookie", "password", "secret", "token")
_INVALID_JSON_RESPONSE_MARKERS = (
    "did not return valid json",
    "jsondecodeerror",
    "expecting ',' delimiter",
    "expecting property name",
    "unterminated string",
)


def _payload(context: dict[str, Any]) -> dict[str, Any]:
    config_payload = as_record(as_record(as_record(context.get("config")).get("inputs")).get("payload"))
    return {**config_payload, **as_record(context.get("payload"))}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _matching_identity(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    target = as_record(payload.get("target_worker"))
    mcp_context = as_record(payload.get("mcp_context"))
    mcp = as_record(mcp_context.get("mcp"))
    if mcp.get("readOnly") is not True:
        raise ValueError("Desktop conversation MCP context must be explicitly read-only.")
    if str(mcp_context.get("schema") or "") != CONTEXT_SCHEMA:
        raise ValueError("Desktop conversation MCP context schema is invalid.")
    for target_key, context_key in (("id", "workerId"), ("jobId", "jobId")):
        expected = str(target.get(target_key) or "").strip()
        observed = str(mcp_context.get(context_key) or "").strip()
        if not expected or expected != observed:
            raise ValueError(f"Desktop conversation target identity mismatch for {target_key}.")
    target_run_id = str(target.get("runId") or "").strip()
    context_run_id = str(mcp_context.get("runId") or "").strip()
    if target_run_id != context_run_id:
        raise ValueError("Desktop conversation target identity mismatch for runId.")
    return target, mcp_context


def _supervision_context(payload: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    context = as_record(payload.get("supervision_context"))
    if str(context.get("schema") or "") != SUPERVISION_SCHEMA:
        raise ValueError("Desktop conversation supervision context schema is invalid.")
    for target_key, context_key in (("id", "workerId"), ("jobId", "jobId")):
        expected = str(target.get(target_key) or "").strip()
        observed = str(context.get(context_key) or "").strip()
        if not expected or expected != observed:
            raise ValueError(f"Desktop conversation supervision identity mismatch for {target_key}.")
    target_run_id = str(target.get("runId") or "").strip()
    context_run_id = str(context.get("runId") or "").strip()
    if target_run_id != context_run_id:
        raise ValueError("Desktop conversation supervision identity mismatch for runId.")
    if encoded_size(context) > MAX_SUPERVISION_CONTEXT_BYTES:
        raise ValueError("Desktop conversation supervision context exceeds the blueprint limit.")
    return context


def _prepared_supervision_context(context: dict[str, Any], *, include_configuration: bool) -> dict[str, Any]:
    runtime = as_record(context.get("runtime"))
    configuration = as_record(context.get("configuration"))
    editable_fields = []
    for candidate in list(configuration.get("editableFields") or [])[:80] if include_configuration else []:
        field = as_record(candidate)
        key = compact_text(field.get("key"), 160)
        if not key:
            continue
        editable_fields.append({
            "key": key,
            "label": compact_text(field.get("label") or key, 240),
            "type": compact_text(field.get("type") or "text", 40),
            "required": field.get("required") is True,
            "currentValue": compact_text(field.get("currentValue"), 4_000),
        })
    return {
        "runtime": {
            "state": compact_text(runtime.get("state"), 80),
            "available": runtime.get("available") if isinstance(runtime.get("available"), bool) else None,
            "message": compact_text(runtime.get("message"), 500),
            "activeStage": compact_text(runtime.get("activeStage") or runtime.get("active_stage"), 160),
            "pendingDecisionCount": _nonnegative_int(runtime.get("pendingDecisionCount")),
            "updatedAt": compact_text(runtime.get("updatedAt"), 80),
        },
        "configuration": {"editableFields": editable_fields},
    }


def _prompt_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return compact_text(value, 500)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if depth >= 2:
        return compact_text(value, 500)
    if isinstance(value, list):
        return [_prompt_value(item, depth=depth + 1) for item in value[:8]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:16]:
            key = compact_text(raw_key, 120)
            if not key or any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
                continue
            result[key] = _prompt_value(item, depth=depth + 1)
        return result
    return compact_text(value, 500)


def _prompt_record(record: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in _CORE_RECORD_KEYS:
        if key in record:
            compact[key] = _prompt_value(record.get(key))
    for key, value in record.items():
        normalized_key = compact_text(key, 120)
        if (
            not normalized_key
            or normalized_key in compact
            or normalized_key in _CORE_RECORD_KEYS
            or any(part in normalized_key.lower() for part in _SENSITIVE_KEY_PARTS)
        ):
            continue
        compact[normalized_key] = _prompt_value(value)
        if len(compact) >= 18:
            break
    return compact


def _question_terms(question: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(question)
        if token.lower() not in _STOP_WORDS
    }


def _selected_prompt_records(records: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    compact_records = [_prompt_record(record) for record in records]
    if len(compact_records) <= MAX_PROMPT_RECORDS:
        return compact_records

    terms = _question_terms(question)
    ranked = sorted(
        enumerate(compact_records),
        key=lambda pair: (
            sum(term in json.dumps(pair[1], sort_keys=True, default=str).lower() for term in terms),
            int(pair[1].get("revision") or 0),
        ),
        reverse=True,
    )
    latest_count = min(4, MAX_PROMPT_RECORDS)
    selected_indexes = {index for index, _record in ranked[: MAX_PROMPT_RECORDS - latest_count]}
    selected_indexes.update(range(len(compact_records) - latest_count, len(compact_records)))
    if len(selected_indexes) < MAX_PROMPT_RECORDS:
        for index, _record in ranked:
            selected_indexes.add(index)
            if len(selected_indexes) >= MAX_PROMPT_RECORDS:
                break
    return [compact_records[index] for index in sorted(selected_indexes)[-MAX_PROMPT_RECORDS:]]


def _prepared_history(payload: dict[str, Any]) -> list[dict[str, str]]:
    history = []
    for candidate in list(payload.get("conversation_history") or [])[-8:]:
        item = as_record(candidate)
        text = compact_text(item.get("text") or item.get("message"), 1_000)
        if not text:
            continue
        history.append({
            "role": "user" if str(item.get("role") or "").lower() == "user" else "worker",
            "text": text,
        })
    return history


def prepare_conversation_context(context: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(context)
    if str(payload.get("schema_version") or "") != REQUEST_SCHEMA:
        raise ValueError("Desktop conversation request schema is invalid.")
    request_id = compact_text(payload.get("request_id"), 220)
    question = compact_text(payload.get("question"), MAX_QUESTION_LENGTH)
    if not request_id or not question:
        raise ValueError("Desktop conversation request id and question are required.")
    target, mcp_context = _matching_identity(payload)
    supervision = _supervision_context(payload, target)
    if encoded_size(mcp_context) > MAX_CONTEXT_BYTES:
        raise ValueError("Desktop conversation MCP context exceeds the blueprint limit.")

    mcp = as_record(mcp_context.get("mcp"))
    records = [as_record(record) for record in list(mcp.get("records") or [])[:MAX_RECORDS]]
    prompt_records = _selected_prompt_records(records, question)
    prepared = {
        "schema_version": REQUEST_SCHEMA,
        "request_id": request_id,
        "question": question,
        "target_worker": {
            "id": compact_text(target.get("id"), 160),
            "blueprintId": compact_text(target.get("blueprintId"), 160),
            "name": compact_text(target.get("name"), 160),
            "mission": compact_text(target.get("mission"), 1_000),
            "jobId": compact_text(target.get("jobId"), 220),
            "runId": compact_text(target.get("runId"), 220),
        },
        "mcp_revision": _nonnegative_int(mcp.get("currentRevision")),
        "conversation_history": _prepared_history(payload),
        "available_record_count": len(records),
        "records": prompt_records,
        "supervision_context": _prepared_supervision_context(
            supervision,
            include_configuration=bool(_CONFIGURATION_TERMS.search(question)),
        ),
    }
    path = Path(context["run_dir"]) / PREPARED_CONTEXT_PATH
    write_json(path, prepared)
    return {
        "prepared_context": PREPARED_CONTEXT_PATH,
        "record_count": len(prompt_records),
        "available_record_count": len(records),
    }


def _fallback_reply(prepared: dict[str, Any]) -> dict[str, Any]:
    records = list(prepared.get("records") or [])
    latest = as_record(records[-1]) if records else {}
    summary = compact_text(
        latest.get("summary") or latest.get("message") or latest.get("stage"),
        1_500,
    )
    if not summary:
        summary = "The current read-only MCP snapshot does not contain enough evidence to answer that yet."
    state = str(latest.get("publication_state") or "staged").lower()
    suffix = " This is final evidence." if state == "final" else " This is staged evidence and may still change."
    record_id = compact_text(latest.get("record_id"), 220)
    return {
        "reply": f"{summary}{suffix}",
        "used_record_ids": [record_id] if record_id else [],
        "configuration_proposal": None,
    }


def _configuration_proposal(response: dict[str, Any], prepared: dict[str, Any]) -> dict[str, Any] | None:
    proposal = as_record(response.get("configuration_proposal") or response.get("configurationProposal"))
    configuration = as_record(as_record(prepared.get("supervision_context")).get("configuration"))
    fields = {
        compact_text(as_record(field).get("key"), 160): as_record(field)
        for field in list(configuration.get("editableFields") or [])
        if compact_text(as_record(field).get("key"), 160)
    }
    changes = []
    seen = set()
    for candidate in list(proposal.get("changes") or [])[:20]:
        change = as_record(candidate)
        key = compact_text(change.get("key"), 160)
        field = fields.get(key)
        value = compact_text(change.get("value") or change.get("to"), 4_000)
        if not field or not value or value == compact_text(field.get("currentValue"), 4_000) or key in seen:
            continue
        seen.add(key)
        changes.append({
            "key": key,
            "value": value,
            "reason": compact_text(change.get("reason") or change.get("rationale"), 1_000),
        })
    if not changes:
        return None
    return {
        "title": compact_text(proposal.get("title") or "Proposed configuration update", 240),
        "summary": compact_text(proposal.get("summary") or proposal.get("reason"), 1_000),
        "changes": changes,
    }


def _llm_usage(client: Any) -> dict[str, Any]:
    usage_snapshot = getattr(client, "usage_snapshot", None)
    if callable(usage_snapshot):
        snapshot = usage_snapshot()
        if isinstance(snapshot, dict):
            return snapshot
    return {
        "provider": compact_text(getattr(client, "provider", "none"), 120),
        "model": compact_text(getattr(client, "model", "none"), 240),
        **{
            key: max(0, int(getattr(client, key, 0) or 0))
            for key in (
                "calls",
                "fallback_calls",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "estimated_tokens",
            )
        },
    }


def _invalid_json_response(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _INVALID_JSON_RESPONSE_MARKERS)


def _generate_model_response(
    client: Any,
    *,
    system_prompt: str,
    prompt_payload: dict[str, Any],
    fallback: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    user_prompt = json.dumps(prompt_payload, sort_keys=True, default=str)
    try:
        return as_record(client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
        )), None
    except Exception as error:
        if not _invalid_json_response(error):
            raise

    retry_prompt = (
        f"{system_prompt}\n"
        "Your previous response could not be parsed. Return only one single-line JSON object "
        "matching the exact example shape. Do not use Markdown, comments, or literal newlines inside strings."
    )
    try:
        return as_record(client.generate_json(
            system_prompt=retry_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
        )), "retried_invalid_json"
    except Exception as error:
        if not _invalid_json_response(error):
            raise
        return fallback, "deterministic_invalid_json_fallback"


def _generate_conversation_response(
    client: Any,
    prepared: dict[str, Any],
    fallback: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    return _generate_model_response(
        client,
        system_prompt=SYSTEM_PROMPT,
        prompt_payload=prepared,
        fallback=fallback,
    )


def _known_record_ids(prepared: dict[str, Any]) -> set[str]:
    return {
        compact_text(as_record(record).get("record_id"), 220)
        for record in list(prepared.get("records") or [])
        if compact_text(as_record(record).get("record_id"), 220)
    }


def _used_record_ids(response: dict[str, Any], prepared: dict[str, Any], fallback: dict[str, Any]) -> list[str]:
    known_ids = _known_record_ids(prepared)
    used_ids = []
    response_ids = response.get("used_record_ids")
    candidates = response_ids if isinstance(response_ids, list) else fallback.get("used_record_ids")
    for value in list(candidates or [])[:20]:
        record_id = compact_text(value, 220)
        if record_id in known_ids and record_id not in used_ids:
            used_ids.append(record_id)
        if len(used_ids) >= 6:
            break
    return used_ids


def _conversation_intent(value: Any) -> str:
    intent = compact_text(value, 40).lower()
    return intent if intent in {"conversation", "monitor", "control"} else "monitor"


def draft_coworker_turn(context: dict[str, Any], llm: Any | None = None) -> dict[str, Any]:
    prepared_path = Path(context["run_dir"]) / PREPARED_CONTEXT_PATH
    if not prepared_path.is_file():
        raise ValueError("Prepared desktop conversation context is missing.")
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    grounded_fallback = _fallback_reply(prepared)
    fallback = {
        "intent": "control" if _CONFIGURATION_TERMS.search(str(prepared.get("question") or "")) else "monitor",
        "draft_reply": grounded_fallback["reply"],
        "used_record_ids": grounded_fallback["used_record_ids"],
        "uncertainties": [],
        "configuration_proposal": None,
    }
    client = conversation_llm(as_record(context.get("config")), llm)
    response, response_recovery = _generate_model_response(
        client,
        system_prompt=COWORKER_TURN_SYSTEM_PROMPT,
        prompt_payload=prepared,
        fallback=fallback,
    )
    usage = _llm_usage(client)
    if response_recovery:
        usage["response_recovery"] = response_recovery
    turn = {
        "schema_version": "otterdesk.coworker_conversation_turn.v1",
        "intent": _conversation_intent(response.get("intent") or fallback["intent"]),
        "draft_reply": compact_text(response.get("draft_reply") or response.get("reply") or fallback["draft_reply"], 20_000),
        "used_record_ids": _used_record_ids(response, prepared, fallback),
        "uncertainties": [
            compact_text(value, 500)
            for value in list(response.get("uncertainties") or [])[:3]
            if compact_text(value, 500)
        ],
        "configuration_proposal": _configuration_proposal(response, prepared),
        "llm": usage,
    }
    write_json(Path(context["run_dir"]) / COWORKER_TURN_PATH, turn)
    return {
        "coworker_turn": COWORKER_TURN_PATH,
        "intent": turn["intent"],
        "source_count": len(turn["used_record_ids"]),
    }


def answer_desktop_conversation(context: dict[str, Any], llm: Any | None = None) -> dict[str, Any]:
    prepared_path = Path(context["run_dir"]) / PREPARED_CONTEXT_PATH
    if not prepared_path.is_file():
        raise ValueError("Prepared desktop conversation context is missing.")
    coworker_turn_path = Path(context["run_dir"]) / COWORKER_TURN_PATH
    if not coworker_turn_path.is_file():
        raise ValueError("The default-LLM co-worker conversation turn is missing.")
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    coworker_turn = json.loads(coworker_turn_path.read_text(encoding="utf-8"))
    grounded_fallback = _fallback_reply(prepared)
    fallback = {
        "reply": compact_text(coworker_turn.get("draft_reply") or grounded_fallback["reply"], 20_000),
        "used_record_ids": list(coworker_turn.get("used_record_ids") or grounded_fallback["used_record_ids"]),
        "configuration_proposal": coworker_turn.get("configuration_proposal"),
    }
    client = conversation_llm(as_record(context.get("config")), llm)
    response, response_recovery = _generate_conversation_response(
        client,
        {"prepared_context": prepared, "coworker_turn": coworker_turn},
        fallback,
    )
    reply = compact_text(response.get("reply") or fallback["reply"], 20_000)
    configuration_proposal = _configuration_proposal(response, prepared)
    used_ids = _used_record_ids(response, prepared, fallback)
    record_by_id = {
        compact_text(as_record(record).get("record_id"), 220): as_record(record)
        for record in list(prepared.get("records") or [])
    }
    sources = [
        f"MCP {compact_text(record_by_id[record_id].get('kind') or 'record', 80)} {record_id} ({compact_text(record_by_id[record_id].get('publication_state') or 'staged', 40)})"
        for record_id in used_ids
    ]
    usage = _llm_usage(client)
    usage["coworker_turn"] = as_record(coworker_turn.get("llm"))
    if response_recovery:
        usage["response_recovery"] = response_recovery
    artifact = {
        "schema_version": OUTPUT_SCHEMA,
        "type": OUTPUT_TYPE,
        "request_id": prepared["request_id"],
        "target_worker": prepared["target_worker"],
        "reply": reply,
        "sources": sources,
        "used_record_ids": used_ids,
        "mcp_revision": prepared["mcp_revision"],
        "read_only": True,
        "configuration_proposal": configuration_proposal,
        "llm": usage,
    }
    write_json(Path(context["run_dir"]) / "final_artifact.json", artifact)
    return {"final_artifact": artifact, "reply": reply, "source_count": len(sources)}


def run_conversation_assistant(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "prepare_conversation_context":
        return prepare_conversation_context(context)
    if step_id == "draft_coworker_turn":
        return draft_coworker_turn(context)
    if step_id == "answer_desktop_conversation":
        return answer_desktop_conversation(context)
    raise ValueError(f"OtterDesk Conversation Assistant does not own step {step_id!r}.")


__all__ = [
    "SYSTEM_PROMPT",
    "answer_desktop_conversation",
    "draft_coworker_turn",
    "prepare_conversation_context",
    "run_conversation_assistant",
]
