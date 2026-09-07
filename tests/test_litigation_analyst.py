from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest
from mn_sdk.blueprints import (
    blueprint_definition,
    compile_blueprint,
    read_blueprint,
    resolve_config,
)
from mn_sdk.step_runtime import StepContext
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "litigation_analyst"
WORKSPACE = companion_workspace(ROOT)


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT / "payloads"))
    for repo in ["mn-skills", "mn-agents"]:
        for path in (WORKSPACE / repo).glob("*/src"):
            monkeypatch.syspath_prepend(str(path))
    return {
        name: importlib.import_module("domain." + name)
        for name in ["intake", "research", "reporting", "sample_data", "indexing"]
    }


def make_context(tmp_path, folder=None):
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    config["investigation"].update(top_k=1, max_model_decisions=30)
    payload = dict(config["inputs"]["payload"])
    if folder is not None:
        payload["input_folder"] = str(folder)
    return {"run_dir": tmp_path / "run", "payload": payload, "config": config}


def protocol_action(ctx):
    phase = ctx["phase"]
    history = ctx["history"]
    if phase == "report_review":
        return "review_report", {"accepted_ids": [f["id"] for f in ctx["report_draft"]["findings"]], "issues": ["Original authenticity remains unverified."]}
    if ctx.get("report_review") is not None:
        return "finish", {"reason": "Relevant enquiry assessed; remaining issues require human review."}
    if phase == "planning":
        if ctx["hypotheses"]:
            h = ctx["hypotheses"][0]
            ids = h["supporting_evidence"] + h["contradictory_evidence"]
            findings = [{"id": "f1", "section": "findings", "title": "Retrieved notice",
                         "assessment": h["assessment"], "evidence_ids": ids,
                         "limitations": "Identity and context remain unresolved."}] if ids else []
            return "submit_report", {"findings": findings, "conclusion_ids": ["f1"] if findings else [], "follow_up": ["Verify identity."]}
        return "plan_enquiry", {"question": "What does the notice establish?", "purpose": "Test awareness.", "existing_findings": "None yet.", "support_sought": "Exact notice.", "counter_evidence_sought": "Routine duties or contradictory dates.", "completion_criteria": "Assess retrieved notice and limitations."}
    if history and history[-1]["action"]["name"] == "update_hypothesis":
        return "review_enquiry", {"finding": "Notice assessed.", "evidence_ids": [], "counter_evidence_result": "Ordinary explanation considered.", "unresolved": ["Verify identity."]}
    return None


class ScriptedModel:
    model = "scripted-offline-test"
    last_usage = {}
    calls = 0

    def completion_text(self, system, user):
        self.calls += 1
        context = json.loads(user)
        control = protocol_action(context)
        if control:
            return json.dumps({"name": control[0], "arguments": control[1], "reason": "Plan, execute, assess, and review."})
        history = [r for r in context["history"] if r["action"]["name"] not in ("plan_enquiry", "review_enquiry")]
        ids = [
            p["evidence_id"]
            for r in history
            for p in r.get("result", {}).get("passages", [])
        ]
        if not history:
            action = ("read_skill", {"skill": "mirrorneuron.document.reading"})
        elif history[-1]["action"]["name"] == "read_skill":
            action = (
                "invoke_skill",
                {
                    "skill": "mirrorneuron.document.reading",
                    "operation": "search",
                    "arguments": {"query": "approval", "top_k": 1},
                },
            )
        elif history[-1]["action"]["name"] == "invoke_skill":
            action = (
                "update_hypothesis",
                {
                    "id": "approval",
                    "question": "Do these records establish approval?",
                    "factual_basis": "The retrieved passage mentions approval.",
                    "supporting_evidence": ids,
                    "contradictory_evidence": [],
                    "alternatives": ["Routine review may explain the record."],
                    "status": "inconclusive",
                    "assessment": "This exact passage requires further human review.",
                    "outstanding_enquiries": ["Verify context and identity."],
                    "parent_id": None,
                },
            )
        else:
            action = (
                "finish",
                {
                    "reason": "Available passage cannot resolve context; human review required."
                },
            )
        return json.dumps(
            {
                "name": action[0],
                "arguments": action[1],
                "reason": "Test the evidence and competing explanation.",
            }
        )


@pytest.fixture(autouse=True)
def graph_engine_stub(monkeypatch, modules):
    # Unit tests exercise ingestion ordering without pretending to execute the Linux engine.
    def project(self, documents):
        self.graph_path.write_bytes(b"test graph fixture")

    monkeypatch.setattr(modules["indexing"].CaseGraphProjector, "project", project)
    monkeypatch.setattr(modules["indexing"].GraphClient, "check", lambda self: "ok")


def test_source_contract_compiles_docker_and_resolvable_workers(modules):
    package = read_blueprint(BLUEPRINT)
    source = blueprint_definition(package)
    assert source["response_service"] == {"enabled": True}
    assert not any(i["required"] for i in source["contracts"]["inputs"].values())
    compiled = compile_blueprint(package, resolve_config(package)).manifest
    assert len(compiled["agents"]["nodes"]) >= 9
    for key, record in source["agents"]["registry"].items():
        assert key not in {s["id"] for s in source["workflow"]["steps"]}
        assert callable(importlib.import_module(record["handler"]).run)
    groups = json.loads((BLUEPRINT / "execution.json").read_text())["workers"]["groups"]
    assert all(g["uses"] == "mn-agents.worker.python_docker@1" for g in groups)
    assert (BLUEPRINT / "payloads/docker_worker/Dockerfile").is_file()


def test_custom_folder_never_downloads_and_freezes_sources(
    modules, tmp_path, monkeypatch
):
    folder = tmp_path / "input"
    folder.mkdir()
    original = "Approval notice. Alternative explanation and reconciliation records."
    (folder / "notice.txt").write_text(original)
    (folder / "opaque.bin").write_bytes(b"\x00\xff")
    monkeypatch.setattr(
        modules["intake"],
        "prepare_emc2",
        lambda *a: pytest.fail("custom input downloaded sample"),
    )
    context = make_context(tmp_path, folder)
    payload, refs = modules["intake"].prepare_sources(context)
    assert payload["document_count"] == 2
    assert payload["unreadable_count"] == 1
    assert all((context["run_dir"] / r["path"]).exists() for r in refs)
    (folder / "notice.txt").write_text("changed after intake")
    model = ScriptedModel()
    modules["indexing"].build_indexes(context)
    modules["research"].investigate(context, llm_client=model)
    payload, refs = modules["reporting"].write_review(context)
    draft = (context["run_dir"] / "final_report.md").read_text()
    assert original in draft
    assert "changed after intake" not in draft
    assert "SHA-256" in draft and "1 of 2 source records" in draft
    assert payload["status"] == "draft_for_human_review"
    assert len(json.dumps(payload)) < 1000
    from domain.evidence.store import EvidenceStore

    store = EvidenceStore(context["run_dir"] / "case/evidence.sqlite3")
    hypotheses = store.hypotheses_for(1)
    assert len(hypotheses) == 1
    assert all(r["query_kind"] == "document" for r in store.query_runs_for(1))
    assert (context["run_dir"] / "case/evidence.rgx").exists()
    previous_calls = model.calls
    modules["indexing"].build_indexes(context)
    modules["research"].investigate(context, llm_client=model)
    assert model.calls == previous_calls
    assert len(store.query_readonly("SELECT id FROM investigations")) == 1


def test_no_input_prepares_sample_automatically(modules, tmp_path, monkeypatch):
    calls = []

    def prepare(destination):
        calls.append(destination)
        destination.mkdir(parents=True)
        (destination / "sample.txt").write_text("Synthetic evidence sample")
        return destination

    monkeypatch.setattr(modules["intake"], "prepare_emc2", prepare)
    context = make_context(tmp_path)
    modules["intake"].prepare_sources(context)
    assert calls == [context["run_dir"] / "sample/emc2"]
    assert json.loads((context["run_dir"] / "case/source_inventory.json").read_text())[
        "sample"
    ]


@pytest.mark.parametrize("kind", ["missing", "empty", "binary_only", "symlink"])
def test_invalid_custom_sources_fail_before_model(modules, tmp_path, kind, monkeypatch):
    folder = tmp_path / "input"
    if kind != "missing":
        folder.mkdir()
    if kind == "binary_only":
        (folder / "opaque.bin").write_bytes(b"\xff")
    if kind == "symlink":
        (folder / "escape.txt").symlink_to(tmp_path / "outside.txt")
    monkeypatch.setattr(
        modules["intake"], "prepare_emc2", lambda *a: pytest.fail("must not download")
    )
    with pytest.raises((ValueError, RuntimeError)):
        modules["intake"].prepare_sources(make_context(tmp_path, folder))


def test_tampered_snapshot_prevents_draft(modules, tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.txt").write_text("Approval reconciliation notice")
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)
    modules["indexing"].build_indexes(context)
    modules["research"].investigate(context, llm_client=ScriptedModel())
    (context["run_dir"] / "case/sources.json").write_text("[]")
    with pytest.raises(ValueError, match="hash mismatch"):
        modules["reporting"].write_review(context)
    assert not (context["run_dir"] / "final_report.md").exists()


def test_shared_agent_replay_is_durable(modules, tmp_path, monkeypatch):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.txt").write_text("Approval notice")
    context = make_context(tmp_path, folder)
    monkeypatch.setenv("MN_RUN_DIR", str(context["run_dir"]))
    monkeypatch.setenv("MN_BLUEPRINT_BUNDLE_DIR", str(BLUEPRINT))
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(tmp_path / "output"))
    worker = importlib.import_module("agents.case_document_examiner")
    invocation = StepContext(
        step_id="prepare_case_sources",
        agent_id="case_document_examiner",
        invocation_id="prepare_case_sources__case_document_examiner",
        job_id="test-job",
        run_id="test-run",
        idempotency_key="test-job/test-run/intake",
        config=context["config"],
        message={"body": {"input_folder": str(folder)}},
    )
    first = worker.run(invocation)
    (folder / "notice.txt").write_text("changed")
    second = worker.run(invocation)
    assert first.outputs == second.outputs
    assert all((context["run_dir"] / r["path"]).exists() for r in first.artifacts)
    snapshot = (context["run_dir"] / "case/sources.json").read_text()
    assert "Approval notice" in snapshot and "changed" not in snapshot
    assert len(json.dumps(first.outputs)) < 2000


def test_architecture_boundaries():
    root = BLUEPRINT / "payloads"
    assert not (root / "agents/domain.py").exists()
    assert not any(root.glob("*_domain"))
    for path in (root / "runtime").glob("*.py"):
        tree = ast.parse(path.read_text())
        assert len(path.read_text().splitlines()) < 500
        assert not any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").split(".")[0] in {"domain", "agents"}
            for n in ast.walk(tree)
        )
    for path in (root / "steps").glob("*.py"):
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").split(".")[0] in {"domain", "agents"}
            for n in ast.walk(tree)
        )
    for path in (root / "agents").glob("*.py"):
        text = path.read_text()
        assert all(
            term not in text
            for term in ["redis", "from_node", "to_node", "complete_step"]
        )


def test_eml_and_office_conversion_preserve_original_hashes(modules, tmp_path):
    import hashlib
    from zipfile import ZipFile

    folder = tmp_path / "input"
    folder.mkdir()
    mail = b"From: sender@example.test\nTo: reviewer@example.test\nSubject: Notice\n\nApproval review notice.\n"
    (folder / "notice.eml").write_bytes(mail)
    with ZipFile(folder / "terms.docx", "w") as doc:
        doc.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        doc.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        doc.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Approval terms require review.</w:t></w:r></w:p></w:body></w:document>',
        )
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)
    inventory = json.loads(
        (context["run_dir"] / "case/source_inventory.json").read_text()
    )
    assert inventory["readable_count"] == 2
    assert (
        next(x for x in inventory["files"] if x["path"] == "notice.eml")["sha256"]
        == hashlib.sha256(mail).hexdigest()
    )
    corpus = modules["intake"].PreparedCorpus(context["run_dir"] / "case", "case")
    assert {d.media_type for d in corpus.scan()} >= {"message/rfc822"}
    assert any("Approval terms" in d.text for d in corpus.scan())


def test_corrupt_and_image_only_pdfs_are_coverage_gaps(modules, tmp_path):
    from pypdf import PdfWriter

    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.txt").write_text("Readable review notice")
    (folder / "broken.pdf").write_bytes(b"not a pdf")
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with (folder / "scan.pdf").open("wb") as output:
        writer.write(output)
    context = make_context(tmp_path, folder)
    result, _ = modules["intake"].prepare_sources(context)
    assert result["unreadable_count"] == 2


def test_invalid_model_json_is_audited_and_not_a_success(modules, tmp_path):

    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.txt").write_text("Review notice")
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)

    class InvalidModel:
        model = "invalid-test"

        def completion_text(self, *args):
            return "not json"

    modules["indexing"].build_indexes(context)
    context["config"]["investigation"]["max_model_decisions"] = 2
    payload, _ = modules["research"].investigate(context, llm_client=InvalidModel())
    assert payload["stop_reason"] == "iteration_limit_exhausted"
    state = json.loads((context["run_dir"] / "case/agent_checkpoint.json").read_text())
    assert len(state["data"]["model_interactions"]) == 2
    assert all("error" in r["result"] for r in state["records"])
    assert state["data"]["hypotheses"] == {}


def test_final_report_export_is_grounded_and_uses_configured_destination(
    modules, tmp_path
):
    folder = tmp_path / "input"
    folder.mkdir()
    quotation = (
        "Approval was routine. No cybersecurity incident was reported in this notice."
    )
    (folder / "notice.txt").write_text(quotation)
    context = make_context(tmp_path, folder)
    context["output_folder"] = tmp_path / "Downloads/litigation_analyst"
    assert (
        context["config"]["outputs"]["folder_path"] == "~/Downloads/litigation_analyst"
    )
    modules["intake"].prepare_sources(context)
    modules["indexing"].build_indexes(context)
    modules["research"].investigate(context, llm_client=ScriptedModel())
    path = context["run_dir"] / "case/investigation.json"
    data = json.loads(path.read_text())
    data["report"]["markdown"] = "FABRICATED ASSERTION: someone confessed."
    path.write_text(json.dumps(data))
    modules["reporting"].write_review(context)
    report = (context["output_folder"] / "final_report.md").read_text()
    assert quotation in report
    assert "FABRICATED ASSERTION" not in report
    assert "## Executive summary" in report
    assert "## Recommended human follow-up" in report
    assert "SHA-256" in report
    assert (context["output_folder"] / "runs/run/case/sources.json").exists()
    assert (context["output_folder"] / "runs/run/final_report.md").exists()


def test_missing_hypotheses_are_reported_as_a_gap(modules, tmp_path):
    from domain.app.review import build_review
    from domain.evidence.store import EvidenceStore

    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    identifier = store.create_investigation(
        "Review available records",
        "case",
        llm_model="test",
        graph_path=tmp_path / "graph.rgx",
    )
    summary = build_review(
        {
            "data": {"investigation_id": identifier, "hypotheses": {}},
            "records": [],
            "stop_reason": "tool_call_budget_exhausted",
        },
        store,
        "Review available records",
    )
    text = summary["report"]["markdown"]
    assert "No structured hypotheses were recorded" in text
    assert "No successful graph examination was recorded" in text
    assert "tool_call_budget_exhausted" in text
    assert summary["report"]["evidence_ids"] == ()


def test_default_download_destination_is_registered_for_runtime_copy(
    tmp_path, monkeypatch
):
    from mn_sdk.submission import prepare_job_submission

    monkeypatch.setenv("HOME", str(tmp_path))
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    manifest = {
        "apiVersion": "mn.workflow/v1",
        "kind": "Workflow",
        "id": "litigation_analyst",
        "contract": {},
        "runtime": {},
        "job_name": "litigation-analyst",
        "agents": {
            "nodes": [
                {
                    "node_id": "report",
                    "config": {
                        "environment": {"MN_BLUEPRINT_CONFIG_JSON": json.dumps(config)}
                    },
                }
            ]
        },
    }
    prepared = prepare_job_submission(
        manifest,
        {},
        shared_storage_root=tmp_path / "shared",
        runtime_shared_storage_root="/remote/shared",
    )
    copies = json.loads(prepared.manifest_json)["metadata"]["mn_storage"]["output_copy"]
    assert any(
        item["target_path"] == str(tmp_path / "Downloads/litigation_analyst")
        for item in copies
    )
