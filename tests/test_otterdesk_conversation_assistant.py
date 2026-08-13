from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "otterdesk_conversation_assistant"
PAYLOADS = BLUEPRINT / "payloads"
DEVELOPMENT_ROOT = (
    ROOT.parent
    if (ROOT.parent / "mn-skills").is_dir()
    else ROOT.parent / "mirror-neuron-set"
)
SKILL_SOURCES = sorted((DEVELOPMENT_ROOT / "mn-skills").glob("*/src"))
AGENT_SOURCES = sorted((DEVELOPMENT_ROOT / "mn-agents").glob("*/src"))


class FakeConversationLLM:
    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict) -> dict:
        assert "read-only MCP job snapshot" in system_prompt
        prepared = json.loads(user_prompt)
        assert prepared["question"] == "How many development emails were sent?"
        assert prepared["supervision_context"]["runtime"]["state"] == "running"
        return {
            "reply": "One development email was sent, according to the final delivery receipt.",
            "used_record_ids": ["development-email-delivery"],
            "configuration_proposal": {
                "title": "Move the next check-in",
                "summary": "Use the newly approved cadence.",
                "changes": [{
                    "key": "monitoring.check_in_hour",
                    "value": "09:30",
                    "reason": "Matches the requested morning review.",
                }],
            },
        }

    def usage_snapshot(self) -> dict:
        return {"provider": "fake-test", "model": "fixture", "calls": 1}


class AttributeOnlyConversationLLM(FakeConversationLLM):
    provider = "live-test"
    model = "gemma4:e2b"
    calls = 1
    fallback_calls = 0
    input_tokens = 10
    output_tokens = 4
    total_tokens = 14
    estimated_tokens = 0

    usage_snapshot = None


class MalformedJsonConversationLLM:
    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, **_: object) -> dict:
        self.calls += 1
        raise RuntimeError("LLM did not return valid JSON: Expecting ',' delimiter")

    def usage_snapshot(self) -> dict:
        return {"provider": "fake-test", "model": "gemma4:e2b", "calls": self.calls}


@pytest.fixture()
def conversation_module():
    inserted = [str(PAYLOADS), *(str(path) for path in SKILL_SOURCES)]
    for value in reversed(inserted):
        sys.path.insert(0, value)
    try:
        module = importlib.import_module("domain.conversation")
        yield module
    finally:
        for value in inserted:
            if value in sys.path:
                sys.path.remove(value)
        for name in list(sys.modules):
            if name == "domain" or name.startswith("domain."):
                sys.modules.pop(name, None)


@pytest.fixture()
def conversation_agent_shared_module():
    inserted = [
        str(PAYLOADS),
        *(str(path) for path in SKILL_SOURCES),
        *(str(path) for path in AGENT_SOURCES),
    ]
    for value in reversed(inserted):
        sys.path.insert(0, value)
    try:
        module = importlib.import_module("agents._shared")
        yield module
    finally:
        for value in inserted:
            if value in sys.path:
                sys.path.remove(value)
        for name in list(sys.modules):
            if name == "agents" or name.startswith("agents."):
                sys.modules.pop(name, None)


def request_payload() -> dict:
    return {
        "schema_version": "otterdesk.conversation_assistant.request.v1",
        "request_id": "desktop-request-1",
        "question": "How many development emails were sent?",
        "target_worker": {
            "id": "gtm_assistant",
            "blueprintId": "gtm_assistant",
            "name": "GTM Assistant",
            "jobId": "gtm-job-1",
            "runId": "gtm-run-1",
        },
        "mcp_context": {
            "schema": "otterdesk.worker_mcp_conversation_context.v1",
            "workerId": "gtm_assistant",
            "jobId": "gtm-job-1",
            "runId": "gtm-run-1",
            "mcp": {
                "readOnly": True,
                "currentRevision": 9,
                "records": [
                    {
                        "kind": "result",
                        "record_id": "development-email-delivery",
                        "revision": 9,
                        "publication_state": "final",
                        "summary": "One approved development email was delivered.",
                        "delivered_count": 1,
                    }
                ],
            },
        },
        "supervision_context": {
            "schema": "otterdesk.worker_supervision_context.v1",
            "workerId": "gtm_assistant",
            "jobId": "gtm-job-1",
            "runId": "gtm-run-1",
            "runtime": {
                "state": "running",
                "available": True,
                "message": "The worker is checking replies.",
                "updatedAt": "2026-08-11T12:00:00.000Z",
            },
            "configuration": {
                "editableFields": [{
                    "key": "monitoring.check_in_hour",
                    "label": "Check-in hour",
                    "type": "text",
                    "required": False,
                    "currentValue": "10:00",
                }],
            },
        },
    }


def test_prepares_identity_checked_context_and_writes_grounded_final_artifact(
    conversation_module,
    tmp_path: Path,
) -> None:
    context = {
        "run_dir": tmp_path,
        "config": {
            "inputs": {"payload": request_payload()},
            "execution": {"quick_test": False},
            "llm": {"mode": "live", "require_live": True},
        },
        "payload": {},
    }

    prepared = conversation_module.prepare_conversation_context(context)
    result = conversation_module.answer_desktop_conversation(
        context,
        llm=FakeConversationLLM(),
    )

    assert prepared == {
        "prepared_context": "workflow_state/conversation_context.json",
        "record_count": 1,
        "available_record_count": 1,
    }
    artifact = result["final_artifact"]
    assert artifact["type"] == "otterdesk_conversation_reply"
    assert artifact["read_only"] is True
    assert artifact["mcp_revision"] == 9
    assert artifact["sources"] == [
        "MCP result development-email-delivery (final)"
    ]
    assert artifact["configuration_proposal"] is None
    assert artifact["llm"]["provider"] == "fake-test"
    assert json.loads((tmp_path / "final_artifact.json").read_text(encoding="utf-8")) == artifact


def test_compacts_large_snapshots_for_a_job_focused_model_prompt(
    conversation_module,
    tmp_path: Path,
) -> None:
    payload = request_payload()
    payload["question"] = "What changed in reply monitoring?"
    payload["target_worker"]["mission"] = "Monitor lifecycle email replies and surface decisions."
    payload["conversation_history"] = [
        {"role": "user", "text": "hello"},
        {"role": "worker", "text": "I am watching the reply queue."},
    ]
    payload["mcp_context"]["mcp"]["records"] = [
        {
            "kind": "status",
            "record_id": f"status-{index}",
            "revision": index,
            "publication_state": "staged",
            "summary": "Reply monitoring found a new response." if index == 3 else f"Routine lifecycle update {index}.",
            "payload": {"detail": "x" * 2_000},
        }
        for index in range(1, 31)
    ]
    context = {"run_dir": tmp_path, "config": {"inputs": {"payload": payload}}, "payload": {}}

    result = conversation_module.prepare_conversation_context(context)
    prepared = json.loads((tmp_path / "workflow_state/conversation_context.json").read_text(encoding="utf-8"))

    assert result == {
        "prepared_context": "workflow_state/conversation_context.json",
        "record_count": 12,
        "available_record_count": 30,
    }
    assert prepared["target_worker"]["mission"] == "Monitor lifecycle email replies and surface decisions."
    assert prepared["conversation_history"][-1]["text"] == "I am watching the reply queue."
    assert any(record["record_id"] == "status-3" for record in prepared["records"])
    assert prepared["supervision_context"]["configuration"]["editableFields"] == []
    assert len(json.dumps(prepared)) < 20_000


def test_recovers_repeated_model_json_formatting_errors_with_grounded_fallback(
    conversation_module,
    tmp_path: Path,
) -> None:
    context = {
        "run_dir": tmp_path,
        "config": {"inputs": {"payload": request_payload()}},
        "payload": {},
    }
    client = MalformedJsonConversationLLM()

    conversation_module.prepare_conversation_context(context)
    result = conversation_module.answer_desktop_conversation(context, llm=client)

    artifact = result["final_artifact"]
    assert client.calls == 2
    assert artifact["reply"] == (
        "One approved development email was delivered. This is final evidence."
    )
    assert artifact["used_record_ids"] == ["development-email-delivery"]
    assert artifact["read_only"] is True
    assert artifact["llm"]["response_recovery"] == "deterministic_invalid_json_fallback"


def test_does_not_mask_non_formatting_model_errors(conversation_module) -> None:
    class UnavailableLLM:
        def generate_json(self, **_: object) -> dict:
            raise RuntimeError("LiteLLM gateway connection refused")

    with pytest.raises(RuntimeError, match="connection refused"):
        conversation_module._generate_conversation_response(
            UnavailableLLM(),
            {"question": "What are you doing?"},
            {"reply": "Unknown", "used_record_ids": [], "configuration_proposal": None},
        )


def test_includes_editable_configuration_only_for_configuration_questions(
    conversation_module,
    tmp_path: Path,
) -> None:
    payload = request_payload()
    payload["question"] = "Change the monitoring check-in to 09:30."
    context = {"run_dir": tmp_path, "config": {"inputs": {"payload": payload}}, "payload": {}}

    conversation_module.prepare_conversation_context(context)
    prepared = json.loads((tmp_path / "workflow_state/conversation_context.json").read_text(encoding="utf-8"))

    assert prepared["supervision_context"]["configuration"]["editableFields"] == [{
        "key": "monitoring.check_in_hour",
        "label": "Check-in hour",
        "type": "text",
        "required": False,
        "currentValue": "10:00",
    }]


def test_rejects_a_target_job_identity_mismatch(conversation_module, tmp_path: Path) -> None:
    payload = request_payload()
    payload["mcp_context"]["jobId"] = "different-job"
    context = {
        "run_dir": tmp_path,
        "config": {"inputs": {"payload": payload}},
        "payload": {},
    }

    with pytest.raises(ValueError, match="identity mismatch for jobId"):
        conversation_module.prepare_conversation_context(context)


def test_records_usage_from_older_runtime_clients_without_a_snapshot_method(
    conversation_module,
) -> None:
    client = AttributeOnlyConversationLLM()

    assert conversation_module._llm_usage(client) == {
        "provider": "live-test",
        "model": "gemma4:e2b",
        "calls": 1,
        "fallback_calls": 0,
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
        "estimated_tokens": 0,
    }


def test_exposes_the_bounded_reply_inline_and_as_a_durable_artifact(
    conversation_agent_shared_module,
) -> None:
    artifact = {
        "type": "otterdesk_conversation_reply",
        "reply": "The worker needs approval.",
        "sources": ["MCP approval approval-1 (staged)"],
        "mcp_revision": 7,
    }

    payload, artifacts = conversation_agent_shared_module.domain_result_payload({
        "final_artifact": artifact,
        "reply": artifact["reply"],
        "source_count": 1,
    })

    assert payload["result"] == {
        "artifact": artifact,
        "reply": artifact["reply"],
        "source_count": 1,
    }
    assert payload["final_artifact"] == {
        "kind": "final_artifact",
        "path": "final_artifact.json",
    }
    assert artifacts == [payload["final_artifact"]]


def test_catalog_marks_the_blueprint_private_and_manifest_keeps_it_read_only() -> None:
    entries = {entry["id"]: entry for entry in json.loads((ROOT / "index.json").read_text(encoding="utf-8"))}
    entry = entries["otterdesk_conversation_assistant"]
    manifest = json.loads((BLUEPRINT / "manifest.json").read_text(encoding="utf-8"))

    assert entry["visibility"] == "internal"
    assert entry["otterdesk_hidden"] is True
    assert manifest["metadata"] == {
        "visibility": "internal",
        "otterdesk_hidden": True,
    }
    assert manifest["workflow"]["execution"]["strategy"] == "serial"
    assert manifest["identity"]["version"] == 6
    assert manifest["llm"]["model"] == "default"
    assert manifest["llm"]["runtime_model"] == "default"
    assert manifest["llm"]["provider"] == "docker_model_runner"
    assert manifest["llm"]["configs"]["primary"]["model"] == "default"
    assert manifest["llm"]["configs"]["primary"]["runtime_model"] == "default"
    assert manifest["llm"]["configs"]["primary"]["provider"] == "docker_model_runner"
    assert manifest["llm"]["configs"]["primary"]["max_tokens"] == 800
    assert "api_base" not in manifest["llm"]["configs"]["primary"]
    default_config = json.loads((BLUEPRINT / "config/default.json").read_text(encoding="utf-8"))
    assert default_config["llm"]["configs"]["primary"]["max_tokens"] == 800
    assert [step["id"] for step in manifest["workflow"]["steps"]] == [
        "prepare_conversation_context",
        "answer_desktop_conversation",
    ]
    assert "perform_target_job_action" in manifest["workflow"]["policy"]["human"]["blocked_actions"]
