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


def test_skill_discovery_survives_working_memory_selection(modules, monkeypatch, tmp_path):
    import pytest
    from test_litigation_analyst import make_context, ScriptedModel
    from domain.app import local_llm
    folder = tmp_path / 'input'
    folder.mkdir()
    (folder / 'notice.txt').write_text('Approval notice for routine review.')
    context = make_context(tmp_path, folder)
    modules['intake'].prepare_sources(context)
    modules['indexing'].build_indexes(context)

    def select_current(self, messages, *, required_fields, **kwargs):
        request = json.loads(messages[1]['content'])
        assert 'Current execution control (authoritative' in messages[0]['content']
        assert json.dumps({'phase': request['phase'], 'allowed_actions': request['control']['allowed_actions']}) in messages[0]['content']
        assert 'recalled records are historical' in messages[0]['content']
        selected = {key: request[key] for key in required_fields if key in request}
        # With no manual read yet, a model must still see exact usable skill IDs.
        assert selected['approved_operations'] == {}
        assert selected['read_manual_hashes'] == {}
        assert any(s['id'] == 'mirrorneuron.document.reading' for s in selected['skills'])
        raise RuntimeError('selection verified')

    monkeypatch.setattr(local_llm.SDKInvestigationModel, 'complete_json', select_current)
    with pytest.raises(RuntimeError, match='selection verified'):
        modules['research'].investigate(context, llm_client=ScriptedModel())
