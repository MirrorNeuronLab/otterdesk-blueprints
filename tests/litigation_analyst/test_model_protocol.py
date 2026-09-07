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
