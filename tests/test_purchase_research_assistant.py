from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_SRC = ROOT.parent / "mn-skills" / "blueprint_support_skill" / "src"
if str(SUPPORT_SRC) not in sys.path:
    sys.path.insert(0, str(SUPPORT_SRC))


def _runner():
    path = ROOT / "purchase_research_assistant" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
    spec = importlib.util.spec_from_file_location("purchase_research_runner_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_purchase_categories_and_public_query_privacy():
    runner = _runner()
    for category in ("property", "rental_property", "car", "airline_ticket", "custom"):
        normalized = runner.normalize_inputs({"purchase_type": category, "item_description": "sample purchase"})
        assert normalized["purchase_type"] == category

    query = runner.build_public_queries(
        runner.normalize_inputs(
            {
                "purchase_type": "car",
                "item_description": "hybrid SUV",
                "location": "Boston",
                "constraints": {"private_financials": "do not search"},
            }
        )
    )
    assert query
    assert all("private_financial" not in item.lower() for item in query)


def test_public_source_block_is_recorded():
    runner = _runner()
    source = runner._source_record(
        url="https://example.test/item",
        title="Provider page",
        snippet="Please solve CAPTCHA to continue",
        status="observed",
        skill="w3m_browser_skill",
        query="sample purchase",
    )
    assert source["status"] == "blocked"
    assert source["retrieved_at"]


def test_purchase_prompts_are_inside_the_uploaded_worker_bundle():
    runner = _runner()

    assert runner.PROMPTS.prompt_dir == (
        ROOT / "purchase_research_assistant" / "payloads" / "document_workflow" / "prompts"
    )
    assert "Purchase Research Review Task" in runner.load_prompt("purchase-review-task.md")
    assert "bounded purchase-research specialist" in runner.load_prompt("recommendation-system.md")


def test_purchase_default_sample_targets_03755_property_search():
    config = json.loads(
        (ROOT / "purchase_research_assistant" / "config" / "default.json").read_text(encoding="utf-8")
    )
    payload = config["inputs"]["payload"]

    assert payload["purchase_type"] == "property"
    assert payload["location"] == "03755"
    assert payload["constraints"] == {
        "property_type": "single-family house",
        "min_bedrooms": 3,
        "zip_code": "03755",
    }
    assert payload["input_folder"] == "purchase_research_assistant/examples/sample_inputs"


def test_purchase_job_output_dir_overrides_worker_local_downloads(monkeypatch, tmp_path):
    runner = _runner()
    runtime_output = tmp_path / "shared" / "outputs" / "purchase"
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(runtime_output))

    assert runner.resolve_output_folder(
        {"output_folder": "~/Download/purchase_research_assistant"},
        {"outputs": {"folder_path": str(tmp_path / "configured")}},
    ) == runtime_output


def test_fake_run_writes_review_only_purchase_bundle(tmp_path):
    runner = _runner()
    output = tmp_path / "outputs"
    result = runner.run_blueprint(
        inputs={
            "purchase_type": "airline_ticket",
            "item_description": "refundable economy ticket",
            "route": "Boston to Lisbon",
            "travel_dates": "2026-09-10 to 2026-09-18",
            "budget": 1200,
            "input_folder": str(ROOT / "purchase_research_assistant" / "examples" / "sample_inputs"),
            "output_folder": str(output),
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path / "runs",
        run_id="purchase-test",
    )
    artifact = result["final_artifact"]
    assert artifact["purchase_type"] == "airline_ticket"
    assert artifact["recommended_action"] in runner.RECOMMENDATIONS
    assert set(runner.BLOCKED_ACTIONS) <= set(artifact["review_boundary"]["blocked_actions"])
    assert {"inputs.json", "events.jsonl", "result.json"} <= set(artifact["source_refs"])
    for name in (
        "purchase_research.json",
        "purchase_research_report.md",
        "evidence.json",
        "research_sources.json",
        "knowledge_rag.json",
        "action_ledger.json",
        "artifact_quality.json",
        "run_health.json",
    ):
        assert (output / name).exists(), name
    json.loads((output / "purchase_research.json").read_text())
