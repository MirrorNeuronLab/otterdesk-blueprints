"""Finished customer reports become complete, provenance-bound chat sources."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore


@pytest.mark.parametrize("blueprint,report_name", [
    ("software_architecture_advisor", "reports/report.md"),
])
def test_finished_report_publication_retains_complete_text_and_run_history(
        tmp_path, monkeypatch, blueprint, report_name):
    payloads = Path(__file__).parents[1] / blueprint / "payloads"
    monkeypatch.syspath_prepend(str(payloads))
    publisher = importlib.import_module("domain.conversation_sources")
    output = tmp_path / "job-output"
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(output))
    saved = []
    for number in (1, 2):
        root = tmp_path / str(number)
        root.mkdir()
        text = f"# Review {number}\n\n## Finding\nA recorded finding. 中🙂\n\n## Limit\nHuman review required.\n"
        (root / report_name).parent.mkdir(parents=True, exist_ok=True)
        (root / report_name).write_text(text, encoding="utf-8")
        (root / "private-audit.json").write_text('{"private":"not a chat subject"}')
        (root / "raw-input.md").write_text("Not a selected report.")
        context = BlockContext(store=CommittedJsonStore(root), invocation_id=f"publication-{number}",
            revision="conversation-test", run_id=f"run/../{number}")
        options = {"output_folder": output}
        records = publisher.publish_outputs(context, **options)
        assert len(records) == 1
        record = records[0]
        target = Path(record["markdown_path"])
        receipt = json.loads(target.with_name(target.name + ".conversion.json").read_text())
        assert record["source_ref"] == report_name and record["complete"] is True
        assert target.read_text().rstrip() == text.rstrip()
        assert receipt["original_sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert receipt["markdown_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert target.is_relative_to(output / "context_sources" / "outputs")
        assert publisher.publish_outputs(context, **options)[0]["reused"] is True
        saved.append((target, target.read_bytes()))
    assert saved[0][0] != saved[1][0]
    assert all(path.read_bytes() == body for path, body in saved)
    assert sorted(p.name for p in output.rglob("*.md")) == [Path(report_name).name + ".md"] * 2


@pytest.mark.parametrize("blueprint,report_name", [
    ("software_architecture_advisor", "reports/report.md"),
])
@pytest.mark.parametrize("unsafe", ["missing", "symlink"])
def test_missing_or_linked_reports_never_create_a_queryable_source(
        tmp_path, monkeypatch, blueprint, report_name, unsafe):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / blueprint / "payloads"))
    publisher = importlib.import_module("domain.conversation_sources")
    root = tmp_path / "run"
    root.mkdir()
    if unsafe == "symlink":
        other = tmp_path / "private.md"
        other.write_text("Private source outside the run.")
        (root / report_name).parent.mkdir(parents=True, exist_ok=True)
        (root / report_name).symlink_to(other)
    output = tmp_path / "output"
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(output))
    context = BlockContext(store=CommittedJsonStore(root), invocation_id="publication",
        revision="conversation-test", run_id="run")
    options = {"output_folder": output}
    with pytest.raises(ValueError, match="complete"):
        publisher.publish_outputs(context, **options)
    assert not output.exists()


def test_architecture_publishes_only_explicit_completed_sections(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "software_architecture_advisor/payloads"))
    publisher = importlib.import_module("domain.conversation_sources")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/report.md").write_text("# Published architecture review\n")
    (tmp_path / "reports/sections").mkdir()
    (tmp_path / "reports/sections/01-finding.md").write_text("# Finding\nComplete supported section.\n")
    (tmp_path / "reports/sections/private-draft.md").write_text("Unpublished draft.")
    context = BlockContext(store=CommittedJsonStore(tmp_path), invocation_id="publication",
        revision="conversation-test", run_id="run")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="complete"):
        publisher.publish_outputs(context, output_folder=output, section_paths=["reports/sections/missing.md"])
    assert not output.exists()
    records = publisher.publish_outputs(context, output_folder=output, section_paths=["reports/sections/01-finding.md"])
    assert {record["source_ref"] for record in records} == {"reports/report.md", "reports/sections/01-finding.md"}
