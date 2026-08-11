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


class FakeConversationLLM:
    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict) -> dict:
        assert "read-only MCP job snapshot" in system_prompt
        prepared = json.loads(user_prompt)
        assert prepared["question"] == "How many development emails were sent?"
        return {
            "reply": "One development email was sent, according to the final delivery receipt.",
            "used_record_ids": ["development-email-delivery"],
        }

    def usage_snapshot(self) -> dict:
        return {"provider": "fake-test", "model": "fixture", "calls": 1}


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
    }
    artifact = result["final_artifact"]
    assert artifact["type"] == "otterdesk_conversation_reply"
    assert artifact["read_only"] is True
    assert artifact["mcp_revision"] == 9
    assert artifact["sources"] == [
        "MCP result development-email-delivery (final)"
    ]
    assert artifact["llm"]["provider"] == "fake-test"
    assert json.loads((tmp_path / "final_artifact.json").read_text(encoding="utf-8")) == artifact


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
    assert [step["id"] for step in manifest["workflow"]["steps"]] == [
        "prepare_conversation_context",
        "answer_desktop_conversation",
    ]
    assert "perform_target_job_action" in manifest["workflow"]["policy"]["human"]["blocked_actions"]
