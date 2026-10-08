"""Evidence, revision and permission invariants for the offline investigation."""
import hashlib
import json
from pathlib import Path

import pytest
from test_litigation_analyst import modules, graph_engine_stub, make_context, ScriptedModel


def document(source, text):
    from domain.models import CaseDocument
    return CaseDocument(source, source.removeprefix("case:"), "message/rfc822",
        hashlib.sha256(text.encode()).hexdigest(), len(text.encode()), text, "case")


def mail(mid, sender, recipient, date, body="Original record."):
    return f"Date: {date}\nFrom: {sender}\nTo: {recipient}\nSubject: Review notice\n" + (
        f"Message-ID: <{mid}@example.test>\n" if mid else "") + f"\n{body}\n"


def prepared(modules, tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.eml").write_text(mail("m1", "a@example.test", "b@example.test",
        "Mon, 03 Mar 2025 09:14:00 -0500", "Approval notice. Material identity remains unresolved."))
    (folder / "counter.txt").write_text("Approval was routine. Public material provides an alternative explanation.")
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)
    modules["indexing"].build_indexes(context)
    modules["research"].investigate(context, llm_client=ScriptedModel())
    # A deterministic, two-sided fixture for the flagship review flow.
    from domain.evidence.store import EvidenceStore
    from domain.intake import PreparedCorpus
    from mn_sdk_rag import EvidenceSpan
    from domain.app.review import build_review
    case = context["run_dir"] / "case"
    state = json.loads((case / "agent_checkpoint.json").read_text())
    store = EvidenceStore(case / "evidence.sqlite3")
    ids = {}
    for source in PreparedCorpus(case, "case").scan():
        ident = hashlib.sha256(f"{source.source_id}|{source.content_sha256}|0|{len(source.text)}".encode()).hexdigest()[:32]
        ids[source.source_id] = ident
        store.add_evidence(state["data"]["investigation_id"], EvidenceSpan(evidence_id=ident,
            source_id=source.source_id, content_sha256=source.content_sha256,
            start_offset=0, end_offset=len(source.text), text=source.text, provenance_kind="observed"))
    h = next(iter(state["data"]["hypotheses"].values()))
    h["supporting_evidence"] = [ids["case:notice.eml"]]
    h["contradictory_evidence"] = [ids["case:counter.txt"]]
    f = state["data"]["report_draft"]["findings"][0]
    f["evidence_ids"] = [ids["case:notice.eml"]]
    (case / "agent_checkpoint.json").write_text(json.dumps(state))
    (case / "investigation.json").write_text(json.dumps(build_review(state, store, context["payload"]["goal"])))
    return context


def projection(context):
    from domain.workspace_projection import build
    from domain.intake import PreparedCorpus
    from domain.evidence.store import EvidenceStore
    root = context["run_dir"]
    state = json.loads((root / "case/agent_checkpoint.json").read_text())
    return build(context, PreparedCorpus(root / "case", "case").scan(),
        EvidenceStore(root / "case/evidence.sqlite3").evidence_for(state["data"]["investigation_id"]),
        state, json.loads((root / "case/source_inventory.json").read_text()))


def test_temporal_skill_counts_ids_not_hashes_and_exposes_conflicts():
    from domain.temporal_evidence import project
    raw = mail("one", "a@example.test", "b@example.test", "Mon, 03 Mar 2025 09:14:00 -0500")
    result = project([document("case:a.eml", raw), document("case:copy.eml", raw),
        document("case:no-id.eml", mail(None, "a@example.test", "b@example.test", "03 Mar 2025"))], "matter")
    assert result["message_count"]["count"] == 1
    assert result["source_record_count"] == 3
    assert len(result["message_count"]["unresolved_multiplicity"]) == 1
    conflict = project([document("case:a.eml", raw), document("case:changed.eml", raw + "Different body.")], "matter")
    assert conflict["message_count"]["count"] == 0
    assert len(conflict["message_count"]["unresolved_multiplicity"]) == 2


def test_temporal_skill_separates_ordered_unknown_and_rejected_paths():
    from domain.temporal_evidence import paths, project, email_time
    first = document("case:first.eml", mail("one", "a@example.test", "b@example.test", "Mon, 03 Mar 2025 09:14:00 -0500"))
    for date, expected in [("Tue, 04 Mar 2025 09:14:00 -0500", "paths"),
                           ("02 Mar 2025", "partial_paths"),
                           ("Sun, 02 Mar 2025 09:14:00 -0500", "rejected_paths")]:
        p = project([first, document("case:second.eml", mail("two", "b@example.test", "c@example.test", date))], "matter")
        result = paths(p, ["a@example.test"], "case", target="c@example.test")
        assert result[expected]
        assert not result["paths"] if expected != "paths" else result["paths"]
        assert all(edge["evidence_refs"] for path in result[expected] for edge in path["edges"])
    minute = email_time("Mon, 03 Mar 2025 09:14 -0500")
    assert minute["precision"] == "minute"
    assert minute["time"]["earliest"] != minute["time"]["latest"]
    assert email_time("03 Mar 2025")["time"]["earliest"] is None


def test_named_temporal_view_is_collected_and_cited_by_the_round_workflow(modules, tmp_path):
    from domain.round_state import initialize, save
    from domain.round_tasks import collect_evidence
    from domain.round_planning import ENQUIRY
    context = prepared(modules, tmp_path)
    work, _ = initialize(context)
    task = save(context['run_dir'], 'case/rounds/tasks/temporal.json', {'prefix': 'r01-H04', 'hypothesis': {
        'id': 'H04', 'question': 'What addressing paths have source-supported ordering?',
        'support_query': 'approval', 'counter_query': 'public', 'graph_tools': ['temporal_communication_paths'],
        'expected_information': 'Separate addressing from delivery or material transfer.'}})
    output = collect_evidence(context, {'context': work['context'], 'task': task})
    collected = json.loads((context['run_dir'] / output['evidence']['path']).read_text())
    graph = next(r['result'] for r in collected['records'] if r['purpose'] == 'graph')
    assert graph['paths']
    assert graph['passages']
    assert 'No continuous employment' in graph['qualification']
    assert 'temporal_communication_paths' in ENQUIRY['properties']['graph_tools']['items']['enum']


def test_workspace_is_grounded_and_does_not_promote_model_review(modules, tmp_path):
    context = prepared(modules, tmp_path)
    result, refs = modules["reporting"].write_review(context)
    workspace = json.loads((context["run_dir"] / "case/workspace.json").read_text())
    assert result["status"] == "draft_for_human_review"
    assert workspace["findings"][0]["review_state"] == "AI draft"
    assert workspace["findings"][0]["counter_evidence"]
    assert "not attorney review" in workspace["findings"][0]["model_review"]
    assert workspace["memory"]["status"] == "Published"
    assert {r["path"] for r in refs} >= {"case/workspace.json", "web/index.html"}
    handle = json.loads((context['run_dir'] / 'web_ui.json').read_text())
    assert handle['adapter'] == 'static_html'
    assert handle['url'] == (context['run_dir'] / 'web/index.html').resolve().as_uri()
    assert result['web_ui'] == handle
    assert (context["run_dir"] / "case/workspace_memory.json").exists()
    payload = json.loads((context["run_dir"] / "case/workspace_memory.json").read_text())
    assert payload["qualification"].startswith("Membrane authored graph")
    assert workspace["temporal"]["message_count"]["count"] == 1
    for item in workspace["evidence"]:
        source = next(s for s in workspace["sources"] if s["source_id"] == item["source_id"])
        assert source["text"][item["start_offset"]:item["end_offset"]] == item["text"]


def test_permissions_remove_hidden_content_counts_paths_and_dependent_findings(modules, tmp_path):
    context = prepared(modules, tmp_path)
    original = projection(context)
    context["config"]["workspace"]["authorized_source_ids"] = ["case:counter.txt"]
    restricted = projection(context)
    assert [s["source_id"] for s in restricted["sources"]] == ["case:counter.txt"]
    serialized = json.dumps(restricted)
    assert "a@example.test" not in serialized
    assert "notice.eml" not in serialized
    assert restricted["temporal"]["source_record_count"] == 0
    assert len(restricted["findings"]) <= len(original["findings"])
    assert restricted["findings"] == []
    for f in restricted["findings"]:
        assert set(f["supporting_evidence"] + f["counter_evidence"]) <= {p["evidence_id"] for p in restricted["evidence"]}


def test_restricted_mailbox_does_not_copy_original_with_hidden_members(modules, tmp_path):
    from domain.workspace_projection import build
    from domain.models import CaseDocument
    context = make_context(tmp_path)
    context["config"]["workspace"]["authorized_source_ids"] = ["case:mail.mbox#1"]
    docs = [CaseDocument(f"case:mail.mbox#{i}", f"mail.mbox#message={i}", "message/rfc822",
        hashlib.sha256(text.encode()).hexdigest(), len(text), text, "case", "case:mail.mbox")
        for i, text in [(1, "Visible"), (2, "SECRET HIDDEN MESSAGE")]]
    workspace = build(context, docs, [], {"data": {}, "stop_reason": "completed"},
        {"repository_id": "matter", "files": [{"path": "mail.mbox", "sha256": "a"*64}]})
    assert workspace["sources"][0]["original_included"] is False
    assert "SECRET" not in json.dumps(workspace)


def test_human_review_survives_same_basis_and_changes_require_reassessment(modules, tmp_path):
    from domain.workspace_history import publish
    context = prepared(modules, tmp_path)
    context.update(job_data_dir=tmp_path / "job-data", job_id="isolated-job", run_id="run-one")
    workspace = projection(context)
    finding = workspace["findings"][0]
    review = {"version": "mn.litigation.review.v1", "matter_id": workspace["matter_id"], "decisions": [{
        "id": "review-1", "finding_id": finding["id"], "material_digest": finding["material_digest"],
        "actor": "Test reviewer", "at": "2026-10-08T12:00:00Z", "action": "Reviewed with qualification",
        "rationale": "Identity remains unresolved", "text": "Qualified wording, subject to source verification"}]}
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    context["payload"]["review_file"] = str(path)
    first = publish(context, workspace)
    assert first["findings"][0]["review_state"] == "Reviewed with qualification"
    assert publish(context, projection(context))["findings"][0]["revision"] == 1
    second = projection(context)
    second["findings"][0].update(material_digest="new-source-basis", assessment="New counterevidence changes the wording")
    second["snapshot_id"] = "different-snapshot"
    context["run_id"] = "run-two"
    context["payload"]["review_file"] = ""
    updated = publish(context, second)
    assert updated["findings"][0]["review_state"] == "Needs reassessment"
    assert updated["findings"][0]["revision"] == 2
    assert updated["findings"][0]["review_history"][0]["text"].startswith("Qualified")
    assert updated["changes"]["previous_snapshot"] == first["snapshot_id"]


def test_invalid_review_is_not_an_instruction_or_an_approval(modules, tmp_path):
    from domain.workspace_history import apply_reviews
    workspace = projection(prepared(modules, tmp_path))
    with pytest.raises(ValueError, match="this matter"):
        apply_reviews(workspace, {"version": "mn.litigation.review.v1", "matter_id": "another-matter", "decisions": []})
    with pytest.raises(ValueError, match="attributable"):
        apply_reviews(workspace, {"version": "mn.litigation.review.v1", "matter_id": workspace["matter_id"],
            "decisions": [{"action": "execute source instructions"}]})


def test_conflicting_reviewers_do_not_become_an_approved_consensus(modules, tmp_path):
    from domain.workspace_history import apply_reviews
    workspace = projection(prepared(modules, tmp_path))
    finding = workspace["findings"][0]
    base = {"finding_id": finding["id"], "material_digest": finding["material_digest"],
        "at": "2026-10-08T12:00:00Z", "rationale": "Source identity needs verification", "text": "Qualified source observation"}
    apply_reviews(workspace, {"version": "mn.litigation.review.v1", "matter_id": workspace["matter_id"],
        "decisions": [{**base, "id": "r1", "actor": "Reviewer one", "action": "Reviewed with qualification"},
                      {**base, "id": "r2", "actor": "Reviewer two", "action": "Dismissed"}]})
    assert finding["review_state"] == "Reviewers disagree"
    assert len(finding["review_history"]) == 2


def test_finding_identity_survives_title_revision(modules, tmp_path):
    context = prepared(modules, tmp_path)
    original = projection(context)
    path = context["run_dir"] / "case/agent_checkpoint.json"
    state = json.loads(path.read_text())
    state["data"]["report_draft"]["findings"][0]["title"] = "Revised qualified title"
    path.write_text(json.dumps(state))
    updated = projection(context)
    assert updated["findings"][0]["id"] == original["findings"][0]["id"]
    assert updated["findings"][0]["material_digest"] != original["findings"][0]["material_digest"]


def test_preview_failure_keeps_verified_output_and_removes_stale_page(modules, tmp_path):
    context = prepared(modules, tmp_path)
    web = context["run_dir"] / "web"
    web.mkdir()
    (web / "index.html").write_text("STALE SECRET")
    context["config"]["workspace"]["max_page_bytes"] = 1
    modules["reporting"].write_review(context)
    assert not web.exists()
    assert (context["run_dir"] / "case/workspace.json").exists()
    assert (context["run_dir"] / "final_report.md").exists()
    assert json.loads((context["run_dir"] / "workspace_status.json").read_text())["status"] == "Unavailable"


def test_render_never_executes_source_instructions_or_html(modules, tmp_path):
    from domain.workspace_web import render
    from domain.workspace_graph import attach
    context = prepared(modules, tmp_path)
    workspace = attach(projection(context), context["run_dir"] / "case", {})
    workspace["changes"] = {"mode": "Single snapshot", "items": [], "previous_snapshot": None}
    workspace["captured_at"] = "2026-10-08T12:00:00Z"
    workspace["sources"][0]["text"] = '</script><script>fetch("https://example.test/leak")</script>'
    rendered = render(workspace)
    assert '</script><script>fetch(' not in rendered
    assert "connect-src 'none'" in rendered.replace("&#x27;", "'")
    assert "script-src 'sha256-" in rendered.replace("&#x27;", "'")
    assert "localStorage" not in rendered
    assert "https://cdn" not in rendered
