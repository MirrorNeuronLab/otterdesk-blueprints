from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    ROOT
    / "vc_assistant"
    / "payloads"
    / "document_workflow"
    / "scripts"
    / "run_blueprint.py"
)
METHOD_IDS = {
    "berkus_method",
    "scorecard_bill_payne_method",
    "risk_factor_summation_method",
    "venture_capital_method",
    "first_chicago_method",
    "comparables_market_multiple_method",
    "cost_to_duplicate_method",
}


def _load_runner():
    spec = importlib.util.spec_from_file_location("vc_early_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_startup_packets(path: Path) -> None:
    alpha = path / "alpha_ai"
    sparse = path / "sparse_labs"
    alpha.mkdir(parents=True)
    sparse.mkdir(parents=True)
    (alpha / "pitch.txt").write_text(
        "\n".join(
            [
                "Company: Alpha AI",
                "Founder team includes domain experts and engineers.",
                "Market: logistics software with a large buyer segment and active competition.",
                "Product: working MVP, prototype, and enterprise demo.",
                "Traction: $250k ARR, five paying customers, pilot growth, retention evidence.",
                "Strategic partner and distribution channel identified.",
                "Risks: sales cycle dependency and competition.",
            ]
        ),
        encoding="utf-8",
    )
    (sparse / "note.txt").write_text(
        "\n".join(
            [
                "Company: Sparse Labs",
                "Market: early developer tooling idea.",
                "No revenue, cost, prototype, case, or comparable detail yet.",
            ]
        ),
        encoding="utf-8",
    )


def test_vc_early_heuristic_filtering_writes_score_only_company_reports(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        runs_root=tmp_path,
        run_id="vc-unit",
    )

    artifact = result["final_artifact"]
    assert result["blueprint_id"] == "vc_assistant"
    assert artifact["type"] == "vc_early_heuristic_analysis_reports"
    assert artifact["report_only"] is True
    assert len(artifact["company_reports"]) == 2
    assert {report["company_slug"] for report in artifact["company_reports"]} == {"alpha-ai", "sparse-labs"}

    for report in artifact["company_reports"]:
        company_dir = outputs / report["company_slug"]
        assert company_dir.exists()
        assert {"analysis.json", "analysis.md", "sources.json", "evidence.json"} <= {path.name for path in company_dir.iterdir()}
        sources = json.loads((company_dir / "sources.json").read_text(encoding="utf-8"))
        assert any(source["skill"] == "w3m_browser_skill" for source in sources)
        assert any("crunchbase.com" in source["url"] or "Crunchbase" in source["query"] for source in sources)
        assert any(source["verification_target"] in {"query_plan", "crunchbase", "search_results"} for source in sources)
        analysis = json.loads((company_dir / "analysis.json").read_text(encoding="utf-8"))
        assert set(analysis["methods"]) == METHOD_IDS
        assert analysis["method_count"] == 7
        for method in analysis["methods"].values():
            assert "score" in method
            assert method["status"] in {"scored", "insufficient_evidence"}
        markdown = (company_dir / "analysis.md").read_text(encoding="utf-8")
        assert "score-only early screening report" in markdown

    sparse = json.loads((outputs / "sparse-labs" / "analysis.json").read_text(encoding="utf-8"))
    assert "insufficient_evidence" in {
        method["status"]
        for method in sparse["methods"].values()
    }
    assert (outputs / "company_index.json").exists()
    assert (outputs / "company_index.md").exists()

    serialized = json.dumps(artifact).lower()
    assert "filter_label" not in serialized
    assert "screening_decision" not in serialized
    assert '"pass"' not in serialized
    assert '"watch"' not in serialized
    assert '"reject"' not in serialized

    run_artifact = json.loads((tmp_path / "vc-unit" / "final_artifact.json").read_text(encoding="utf-8"))
    assert run_artifact["method_ids"] == list(runner.METHOD_IDS)
