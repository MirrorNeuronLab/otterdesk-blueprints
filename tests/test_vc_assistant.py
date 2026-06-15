from __future__ import annotations

import importlib.util
import json
import threading
import time
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
    assert [report["company_slug"] for report in artifact["company_reports"]] == ["alpha-ai", "sparse-labs"]

    for report in artifact["company_reports"]:
        company_dir = outputs / report["company_slug"]
        assert company_dir.exists()
        assert {
            "analysis.json",
            "analysis.md",
            "method_scores.json",
            "research_sources.json",
            "sources.json",
            "evidence.json",
            "warnings.json",
        } <= {path.name for path in company_dir.iterdir()}
        sources = json.loads((company_dir / "research_sources.json").read_text(encoding="utf-8"))
        assert any(source["skill"] == "w3m_browser_skill" for source in sources)
        assert any("crunchbase.com" in source["url"] or "Crunchbase" in source["query"] for source in sources)
        assert any(source["verification_target"] in {"company_identity_researcher", "crunchbase", "search_results"} for source in sources)
        analysis = json.loads((company_dir / "analysis.json").read_text(encoding="utf-8"))
        method_scores = json.loads((company_dir / "method_scores.json").read_text(encoding="utf-8"))
        assert set(analysis["methods"]) == METHOD_IDS
        assert set(method_scores) == METHOD_IDS
        assert analysis["method_count"] == 7
        for method in analysis["methods"].values():
            assert {"score", "inputs_used", "formula_or_weighting", "assumptions", "source_refs", "warnings"} <= set(method)
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
    assert (outputs / "company_work_queue.json").exists()
    assert (outputs / "research_coverage.json").exists()
    assert (outputs / "method_coverage.json").exists()
    assert (outputs / "run_summary.md").exists()
    assert sorted(path.name for path in (outputs / "company_fact_tables").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]
    assert sorted(path.name for path in (outputs / "research_ledgers").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]
    assert sorted(path.name for path in (outputs / "method_scores").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]
    assert sorted(path.name for path in (outputs / "audit_findings").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]

    serialized = json.dumps(artifact).lower()
    assert "filter_label" not in serialized
    assert "screening_decision" not in serialized
    assert '"pass"' not in serialized
    assert '"watch"' not in serialized
    assert '"reject"' not in serialized

    run_artifact = json.loads((tmp_path / "vc-unit" / "final_artifact.json").read_text(encoding="utf-8"))
    assert run_artifact["method_ids"] == list(runner.METHOD_IDS)
    assert set(run_artifact["workflow_step_ids"]) == set(runner.WORKFLOW_STEP_IDS)
    assert {item["status"] for item in run_artifact["company_work_queue"]} == {"new_or_changed"}

    repeat = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        runs_root=tmp_path,
        run_id="vc-repeat",
    )
    assert {item["status"] for item in repeat["final_artifact"]["company_work_queue"]} == {"unchanged_skipped"}
    assert repeat["final_artifact"]["monitor_state"]["processed_company_count"] == 0
    assert repeat["final_artifact"]["monitor_state"]["skipped_company_count"] == 2
    assert {report["processing_status"] for report in repeat["final_artifact"]["company_reports"]} == {"unchanged_skipped"}


def test_changed_company_packets_process_in_parallel_with_stable_output_order(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    started: set[str] = set()
    lock = threading.Lock()
    two_started = threading.Event()
    original_research = runner.research_company_by_stage

    def fake_research(company, config, run_dir=None):
        with lock:
            started.add(company)
            if len(started) >= 2:
                two_started.set()
        assert two_started.wait(1.0), "changed company packets did not overlap"
        time.sleep(0.02)
        slug = runner.slugify(company)
        return {
            stage: [
                {
                    "company": company,
                    "query": f"{company} {stage}",
                    "url": f"https://example.com/{slug}/{stage}",
                    "title": stage,
                    "snippet": "founder market customer revenue product prototype competitor patent funding investor",
                    "status": "ok",
                    "skill": "w3m_browser_skill",
                    "verification_target": stage,
                    "warning": "",
                    "retrieved_at": runner.utc_now_iso(),
                }
            ]
            for stage in runner.RESEARCH_STAGE_IDS
        }

    runner.research_company_by_stage = fake_research
    try:
        result = runner.run_blueprint(
            inputs={
                "document_folder": str(docs),
                "output_folder": str(outputs),
                "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
            },
            config={"execution": {"max_company_workers": 2}, "scoring": {"max_workers": 7}},
            runs_root=tmp_path,
            run_id="vc-parallel",
        )
    finally:
        runner.research_company_by_stage = original_research

    artifact = result["final_artifact"]
    assert len(started) == 2
    assert artifact["parallel_execution"]["max_company_workers"] == 2
    assert artifact["parallel_execution"]["max_scoring_workers"] == 7
    assert artifact["parallel_execution"]["company_processing_order"] == ["alpha-ai", "sparse-labs"]
    assert [report["company_slug"] for report in artifact["company_reports"]] == ["alpha-ai", "sparse-labs"]


def test_research_ledgers_emit_stage_specific_records_without_browser_network(tmp_path):
    runner = _load_runner()
    original_w3m = runner._append_w3m_research
    original_target = runner._append_target_url_research

    def fake_w3m(sources, *, company, plan, internet, run_dir, verification_target="search_result_or_public_source"):
        sources.append(
            {
                "company": company,
                "query": plan["queries"][0],
                "url": f"https://example.com/{runner.slugify(company)}/{verification_target}",
                "title": verification_target,
                "snippet": f"public {verification_target} evidence",
                "status": "ok",
                "skill": "w3m_browser_skill",
                "verification_target": verification_target,
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            }
        )

    def fake_target(sources, *, company, plan, internet, run_dir):
        sources.append(
            {
                "company": company,
                "query": plan["queries"][0],
                "url": f"https://www.crunchbase.com/organization/{runner.slugify(company)}",
                "title": "Crunchbase profile",
                "snippet": "public profile source",
                "status": "ok",
                "skill": "w3m_browser_skill",
                "verification_target": "crunchbase",
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            }
        )

    runner._append_w3m_research = fake_w3m
    runner._append_target_url_research = fake_target
    try:
        ledger = runner.research_company_by_stage(
            "Example AI",
            {
                "internet_research": {
                    "enabled": True,
                    "max_stage_workers": 5,
                    "default_source_urls": ["https://example.com/reference"],
                    "rendered_browser": {"enabled": False},
                }
            },
            run_dir=tmp_path,
        )
    finally:
        runner._append_w3m_research = original_w3m
        runner._append_target_url_research = original_target

    assert set(ledger) == set(runner.RESEARCH_STAGE_IDS)
    for stage in runner.RESEARCH_STAGE_IDS:
        assert any(source["verification_target"] == stage for source in ledger[stage])
    assert any("funding" in source["query"].lower() for source in ledger["funding_researcher"])
    assert any("competitors" in source["query"].lower() for source in ledger["market_comp_researcher"])
    assert any("customers" in source["query"].lower() for source in ledger["traction_verifier"])
    assert any(source["verification_target"] == "crunchbase" for source in ledger["company_identity_researcher"])
    assert any(source["status"] == "disabled" for source in ledger["rendered_page_researcher"])


def test_scorecard_and_comparables_ignore_non_substantive_defaults():
    runner = _load_runner()
    records = [
        {
            "path": "empty.txt",
            "filename": "empty.txt",
            "company_name": "Empty Co",
            "sha256": "0",
            "suffix": ".txt",
            "text_preview": "Company: Empty Co.",
            "character_count": 18,
            "extraction_method": "embedded_text",
            "ocr_required": False,
            "warnings": [],
        }
    ]
    ledger = {
        stage: [
            {
                "company": "Empty Co",
                "query": f"Empty Co {stage}",
                "url": "research_plan",
                "title": "planned",
                "snippet": "planned public research",
                "status": "planned",
                "skill": "research_planner",
                "verification_target": stage,
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            },
            {
                "company": "Empty Co",
                "query": f"Empty Co {stage}",
                "url": "https://example.com/reference",
                "title": "reference",
                "snippet": "market competitor revenue configured reference text",
                "status": "configured_reference",
                "skill": "w3m_browser_skill",
                "verification_target": stage,
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            },
        ]
        for stage in runner.RESEARCH_STAGE_IDS
    }

    analysis = runner.build_company_analysis("Empty Co", records, ledger, scoring_workers=7)
    assert analysis["methods"]["scorecard_bill_payne_method"]["status"] == "insufficient_evidence"
    assert analysis["methods"]["scorecard_bill_payne_method"]["score"] is None
    assert analysis["methods"]["comparables_market_multiple_method"]["status"] == "insufficient_evidence"
    assert analysis["methods"]["comparables_market_multiple_method"]["score"] is None
    assert analysis["fact_table"]["raw_counts"]["substantive_research_source_count"] == 0
