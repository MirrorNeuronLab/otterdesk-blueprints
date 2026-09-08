from types import SimpleNamespace
import json
from test_litigation_analyst import modules, graph_engine_stub


def test_production_transport_requests_json_without_hidden_model_retries(
    modules, monkeypatch
):
    from domain.app import local_llm
    from mn_sdk.llm import LLMClient

    captured = []

    def complete(system, user, *, config):
        captured.append(config)
        return SimpleNamespace(
            content=json.dumps({"name": "finish", "arguments": {}, "reason": "done"}),
            usage={"provider_response_count": 1},
        )

    monkeypatch.setattr(local_llm, "completion_json_result", complete)
    client = LLMClient(model="test", num_retries=9)
    result = local_llm.SDKInvestigationModel(client).complete_json(
        [{"role": "system", "content": "test"}, {"role": "user", "content": "{}"}]
    )
    assert captured[0].num_retries == 0
    assert result.value["name"] == "finish"
    assert result.usage["provider_response_count"] == 1
    assert client.num_retries == 9


def test_managed_context_binds_each_litigation_decision_and_propagates_partition(modules, monkeypatch):
    from contextlib import contextmanager
    import pytest
    from domain.app import local_llm
    from mn_sdk.llm import LLMClient
    from mn_sdk.context_session import NeedsPartition
    observed = []
    class Memory:
        policy = SimpleNamespace(output_tokens=2048)
        @contextmanager
        def turn(self, invocation, **kwargs):
            observed.append((invocation, kwargs))
            yield
    def partition(system, user, *, config):
        raise NeedsPartition({"reason":"irreducible_review_evidence"})
    monkeypatch.setattr(local_llm, "completion_json_result", partition)
    adapter = local_llm.SDKInvestigationModel(LLMClient(model="test"), context_session=Memory())
    with pytest.raises(NeedsPartition):
        adapter.complete_json([{"role":"system","content":"review"},{"role":"user","content":"{}"}], invocation_id="decision-17", focus="review exact sources", required_fields=["review_evidence"], final=True)
    assert observed == [("decision-17", {"focus":"review exact sources", "required_fields":["review_evidence"], "final":True})]


def test_context_output_budget_caps_provider_reserve(modules, monkeypatch):
    from contextlib import nullcontext
    from domain.app import local_llm
    from mn_sdk.llm import LLMClient
    from mn_sdk.context_session import ContextPolicy
    captured = []
    policy = ContextPolicy(window_tokens=16384, output_tokens=2048)
    memory = SimpleNamespace(policy=policy, turn=lambda *a, **k: nullcontext())

    def complete(system, user, *, config):
        captured.append(config.max_tokens)
        # The failed run required 9,698 input tokens. An 8,192-token
        # provider reserve incorrectly reduced the input budget to 7,680.
        assert policy.window_tokens - config.max_tokens - policy.safety_tokens >= 9698
        return SimpleNamespace(content='{"name":"list_skills","arguments":{}}', usage={})

    monkeypatch.setattr(local_llm, 'completion_json_result', complete)
    for limit in (8192, 1024):
        client = LLMClient(model='test', max_tokens=limit)
        local_llm.SDKInvestigationModel(client, context_session=memory).complete_json(
            [{'role':'system','content':'test'}, {'role':'user','content':'{}'}]
        )
        assert client.max_tokens == limit
    assert captured == [2048, 1024]
