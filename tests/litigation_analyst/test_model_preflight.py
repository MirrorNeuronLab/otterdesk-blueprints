"""Readiness uses the selected model's real request budget before reading a case."""

import json

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk.llm import LLMClient
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from test_litigation_analyst import BLUEPRINT


@pytest.fixture
def context(tmp_path):
    return BlockContext(CommittedJsonStore(tmp_path / "run"), "preflight", "test-v1",
        config=resolve_config(read_blueprint(BLUEPRINT)).data,
        job_id="preflight-job", run_id="preflight-run")


def receipt(context):
    return json.loads(context.store.path("case/model_preflight.json").read_text())


def response(value):
    return {"choices": [{"message": {"content": json.dumps(value)}}]}


def test_default_preflight_accepts_model_latency_beyond_ten_seconds(context, monkeypatch):
    from domain.model_preflight import check

    client = LLMClient(model="registered-model", provider="litellm",
        api_base="http://gateway.test/v1", timeout_seconds=180, max_tokens=8192, strict=True)
    monkeypatch.setattr(LLMClient, "from_env", lambda **kwargs: client)
    calls = []

    def request(purpose, model, path, payload, **options):
        calls.append(options)
        # Simulate a healthy model needing twelve seconds, without sleeping.
        if options["timeout_seconds"] < 12:
            raise TimeoutError("model is still generating")
        assert model == client.model and options["provider"] == client.provider
        assert options["api_base"] == client.api_base
        assert json.loads(payload["messages"][1]["content"]) == {
            "task": "Return ready=true. No case evidence is supplied."}
        assert payload["max_tokens"] == context.config["context_memory"]["policy"]["output_tokens"]
        return response({"ready": True})

    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", request)
    check(context)
    check(context)
    assert len(calls) == 1  # Durable success replays without another model request.
    assert receipt(context)["status"] == "ready"
    assert receipt(context)["request_timeout_seconds"] == 180
    assert receipt(context)["case_evidence_sent"] is False
    assert receipt(context)["fallback_model"] is None


@pytest.mark.parametrize("cap,model_timeout,expected", [(25, 180, 25), (180, 5, 5), (None, 45, 45)])
def test_explicit_preflight_cap_never_extends_model_timeout(context, monkeypatch, cap, model_timeout, expected):
    from domain.model_preflight import check

    context.config["model_preflight"]["timeout_seconds"] = cap
    client = LLMClient(timeout_seconds=model_timeout, strict=True)

    def request(*args, **options):
        assert options["timeout_seconds"] == expected
        return response({"ready": True})

    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", request)
    check(context, client)
    assert client.timeout_seconds == model_timeout
    assert receipt(context)["request_timeout_seconds"] == expected


@pytest.mark.parametrize("timeout", [True, 0, -1, "10", float("nan"), float("inf")])
def test_invalid_preflight_cap_fails_before_model_dispatch(context, monkeypatch, timeout):
    from domain.model_preflight import check

    context.config["model_preflight"]["timeout_seconds"] = timeout
    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", lambda *a, **kw: pytest.fail("Dispatched invalid settings"))
    with pytest.raises(ValueError, match="positive finite number"):
        check(context, LLMClient())


@pytest.mark.parametrize("timed_out", [True, False])
def test_failed_request_retains_safe_actionable_reason(context, monkeypatch, timed_out):
    from domain.model_preflight import check

    def request(*args, **options):
        if timed_out:
            try:
                raise TimeoutError("private endpoint and credential")
            except TimeoutError as error:
                raise RuntimeError("private provider detail") from error
        raise RuntimeError("private provider detail")

    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", request)
    with pytest.raises(ValueError, match="no fallback") as failure:
        check(context, LLMClient(timeout_seconds=180, strict=True))
    saved = receipt(context)
    assert saved["status"] == "unavailable"
    assert saved["reason"] == ("request_timeout" if timed_out else "model_check_failed")
    assert ("timed out" in str(failure.value)) is timed_out
    assert saved["request_timeout_seconds"] == 180
    assert saved["case_evidence_sent"] is False and saved["fallback_model"] is None
    assert "private" not in json.dumps(saved) + str(failure.value)
    assert not context.store.path("case/model_preflight_decision.json").exists()


def test_preflight_requires_valid_readiness_output(context, monkeypatch):
    from domain.model_preflight import check

    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", lambda *a, **kw: response({"ready": False}))
    with pytest.raises(ValueError, match="readiness check failed"):
        check(context, LLMClient(strict=True))
    assert receipt(context)["status"] == "unavailable"
    assert receipt(context)["reason"] == "model_check_failed"
