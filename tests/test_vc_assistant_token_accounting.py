from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "vc_assistant" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("vc_token_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.runtime


def test_vc_manifest_workers_do_not_expose_legacy_token_budget():
    manifest = json.loads((ROOT / "vc_assistant" / "manifest.json").read_text(encoding="utf-8"))
    for binding in manifest.get("runtime", {}).get("bindings", {}).values():
        for worker in binding.get("workers") or []:
            assert "tokens" not in worker


def test_budgeted_llm_records_token_usage_and_dmr_metadata(tmp_path):
    runner = _load_runner()

    class LiveDMRLLM:
        provider = "docker_model_runner"
        model = "medium"
        api_base = "http://spark:12434/engines/v1"
        strict = False
        calls = 0
        fallback_calls = 0
        input_tokens = 17
        output_tokens = 5
        total_tokens = 22
        estimated_tokens = 0
        last_usage = {
            "input_tokens": 17,
            "output_tokens": 5,
            "total_tokens": 22,
            "estimated": False,
            "provider": provider,
            "model": model,
            "source": "provider",
        }

        def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
            self.calls += 1
            response = dict(fallback)
            response.update({"provider": self.provider, "model": self.model, "summary": "Live DMR review."})
            return response

    wrapped = LiveDMRLLM()
    llm = runner.BudgetedLLM(
        wrapped,
        runner.ActionBudget(10),
        require_live=True,
        limiter=runner.LlmCallLimiter(max_concurrent_calls=1, min_interval_seconds=0),
        run_dir=tmp_path,
        heartbeat_seconds=0,
    )

    llm.generate_json(system_prompt="system", user_prompt="{}", fallback={"actor_id": "funding_researcher"})

    assert wrapped.strict is True
    trace_records = [json.loads(line) for line in (tmp_path / "llm_rag_trace.jsonl").read_text().splitlines()]
    completed = [record["payload"] for record in trace_records if record["type"] == "observability_operation_completed"]
    assert completed[-1]["provider"] == "docker_model_runner"
    assert completed[-1]["api_base_kind"] == "docker_model_runner"
    assert completed[-1]["total_tokens"] == 22
    assert completed[-1]["usage_estimated"] is False
    assert completed[-1]["usage_source"] == "provider"

    resource_records = [json.loads(line) for line in (tmp_path / "resources.jsonl").read_text().splitlines()]
    assert resource_records[-1]["type"] == "llm_usage"
    assert resource_records[-1]["payload"]["total_tokens"] == 22
    assert resource_records[-1]["payload"]["api_base_kind"] == "docker_model_runner"
