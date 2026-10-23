"""Research output schemas reach the provider and reject unusable live answers."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_sdk.llm import LLMClient

ROOT = Path(__file__).resolve().parents[1] / "research_assistant"
SOURCE = {
    "source_assessments": [{
        "source_ref": "local:notes.md", "source_type": "local_document",
        "relevant_observations": ["A matched baseline is missing."],
        "limitations": ["One source."], "use_in_synthesis": "Context for a proposed test.",
    }],
    "cross_source_agreements": [], "cross_source_tensions": [], "evidence_gaps": ["Matched baseline."],
}


@pytest.fixture
def model(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    modules = {name: importlib.import_module("domain." + name) for name in ("autonomous", "model", "model_contracts")}
    client = LLMClient(provider="litellm", model="default", api_base="https://unused.invalid/v1",
        strict=True, max_tokens=4096, num_retries=0,
        structured_output_options={"chat_template_kwargs": {"enable_thinking": False}})
    block = SimpleNamespace(config={"llm": {"require_live": True}, "budgets": {"max_llm_calls": 3}},
        store=SimpleNamespace(run_dir=tmp_path), resources={})
    llm, budget = modules["model"].init_research_llm(block, client)
    return modules, llm, client, budget


def source_call(modules, llm, trace):
    return modules["autonomous"]._phase_generate_json(
        llm, phase="source_analysis", instruction="Read the source.",
        context={"source_refs": ["local:notes.md"]}, fallback={"source_assessments": []}, phase_trace=trace,
    )


def test_research_retries_schema_invalid_json_using_the_declared_contract(model, monkeypatch):
    modules, llm, client, budget = model
    replies = iter([{"source_assessments": []}, SOURCE])
    sent = []
    def request(_purpose, _model, _path, payload, **kwargs):
        sent.append(payload)
        return {"choices": [{"message": {"content": json.dumps(next(replies))}}]}
    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", request)
    trace = []
    result = source_call(modules, llm, trace)
    assert result["source_assessments"] == SOURCE["source_assessments"]
    assert len(sent) == 2
    schema = sent[0]["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["name"] == "research_source_analysis"
    assert schema["schema"]["additionalProperties"] is False
    assert schema["schema"]["properties"]["source_assessments"]["items"]["properties"]["source_ref"]["enum"] == ["local:notes.md"]
    assert sent[1]["response_format"] == sent[0]["response_format"]
    assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert client.fallback_calls == 0
    assert budget.used == 1
    assert trace[0]["status"] == "completed"


@pytest.mark.parametrize("reply", [{}, {**SOURCE, "source_assessments": [{**SOURCE["source_assessments"][0], "source_ref": "invented"}]}])
def test_invalid_live_research_never_becomes_a_completed_phase(model, monkeypatch, reply):
    modules, llm, client, _budget = model
    calls = []
    def request(*args, **kwargs):
        calls.append(True)
        return {"choices": [{"message": {"content": json.dumps(reply)}}]}
    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", request)
    trace = []
    with pytest.raises(RuntimeError, match="research_phase:source_analysis.*declared application contract"):
        source_call(modules, llm, trace)
    assert len(calls) == 2
    assert trace == []
    assert client.fallback_calls == 0


def test_specialist_reviews_also_receive_a_schema(model, monkeypatch):
    _modules, llm, _client, _budget = model
    reply = {"actor_id": "reviewer", "role": "Skeptic", "summary": "Evidence is limited.",
        "findings": [], "risks": ["Missing baseline."], "recommended_next_step": "Review the baseline.", "confidence": 0.5}
    sent = []
    def request(_purpose, _model, _path, payload, **kwargs):
        sent.append(payload)
        return {"choices": [{"message": {"content": json.dumps(reply)}}]}
    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", request)
    assert llm.generate_json(system_prompt="Review", user_prompt="Evidence", fallback=reply)["summary"] == reply["summary"]
    schema = sent[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["actor_id"]["const"] == "reviewer"
    assert schema["properties"]["confidence"]["type"] == "number"


@pytest.mark.parametrize("phase", [
    "source_analysis", "question_decomposition", "competing_hypothesis_generation",
    "adversarial_review_H1", "gap_and_probe_planning", "evidence_and_probe_revision",
    "experiment_design_H1", "meta_review_and_ranking", "executive_synthesis",
])
def test_each_research_phase_has_a_closed_valid_contract(model, phase):
    from jsonschema import Draft202012Validator
    modules, *_ = model
    context = {"source_refs": ["local:notes.md"], "hypothesis": {"hypothesis_id": "H1"},
        "candidate_hypotheses": [{"hypothesis_id": "H1"}], "available_tools": ["document_extract", "hypothesis_rank"]}
    schema = modules["model_contracts"].phase_schema(phase, context)
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert not Draft202012Validator(schema).is_valid({})


def test_research_rejects_repeated_source_and_ranking_identities(model):
    modules, *_ = model
    validate = modules["model_contracts"].validate_phase
    assert validate("source_analysis", {}, {"source_assessments": SOURCE["source_assessments"] * 2}) is None
    context = {"candidate_hypotheses": [{"hypothesis_id": "H1"}, {"hypothesis_id": "H2"}]}
    assert validate("meta_review_and_ranking", context,
        {"ranking": [{"hypothesis_id": "H1", "rank": 1}, {"hypothesis_id": "H1", "rank": 2}]}) is None
    assert validate("meta_review_and_ranking", context,
        {"ranking": [{"hypothesis_id": "H1", "rank": 1}, {"hypothesis_id": "H2", "rank": 1}]}) is None
