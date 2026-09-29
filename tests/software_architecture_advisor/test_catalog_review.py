"""Real SDK scheduling, bounded prompts, durable attempts and report traceability."""

import hashlib
import json
from pathlib import Path
import pytest


@pytest.fixture
def run(tmp_path, monkeypatch, architecture_paths):
    monkeypatch.setenv("MN_WORKFLOW_RUN_ID", "test-runtime-run")
    monkeypatch.setenv("MN_JOB_SHARED_STORAGE_ROOT", str(tmp_path / "submission"))
    from domain.catalog_contract import load_catalog

    catalog = load_catalog()
    for module in ["catalog_planning", "opencode_review", "catalog_reporting", "review_admission"]:
        monkeypatch.setattr("domain." + module + ".load_catalog", lambda: catalog)
    from domain.catalog_planning import initializer

    cfg = json.loads(
        (
            Path(__file__).parents[2]
            / "software_architecture_advisor/config/default.json"
        ).read_text()
    )
    cfg["offline"] = False
    source = "def charge(amount):\n    gateway.charge(amount)\n    return amount\n"
    sources = {
        f"src/module {n}.py": {
            "text": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
        for n in range(3)
    }
    snapshot = {
        "id": "fixture",
        "sources": {p: s["sha256"] for p, s in sources.items()},
        "modules": {},
        "input": {"kind": "fixture"},
        "coverage": {"skipped": {}},
        "warnings": [],
    }
    root = tmp_path / "run"
    folder = root / "evidence/snapshots/fixture"
    folder.mkdir(parents=True)
    (root / "snapshot.json").write_text(json.dumps(snapshot))
    (folder / "sources.json").write_text(json.dumps(sources))
    ctx = {
        "run_dir": str(root),
        "config": cfg,
        "payload": {"goal": "Review charge boundary"},
    }
    value, _ = initializer(ctx)
    return ctx, value["context"]


def fake(prompt, *, followup=False):
    p = json.loads(prompt)
    task = p["task"]
    value = {
        "task_id": task["task_id"],
        "kind": task["kind"],
        "status": "completed",
        "scope": "Only supplied frozen source spans",
        "conclusion": "The supplied scope contains an external charge call; runtime effects are unknown.",
        "limitations": ["Runtime behavior was not measured."],
        "observations": [],
        "claims": [],
        "recommendations": [],
        "verification_tasks": [],
        "assumptions": [],
        "work_packages": [],
        "proposed_followups": [],
    }
    if p["evidence"]:
        value["claims"] = [
            {
                "claim_id": "C1",
                "statement": "The supplied source calls gateway.charge.",
                "claim_type": "observed",
                "confidence": "high",
                "rationale": "Exact frozen source span",
                "counterevidence": "Runtime behavior was not observed.",
                "finding": True,
                "evidence": [p["evidence"][0]["id"]],
            }
        ]
    if task["kind"] in {"source_scan", "evidence_followup"} and p["evidence"]:
        value["observations"] = [
            {
                "observation_id": "O1",
                "summary": "External charge call",
                "evidence": [p["evidence"][0]["id"]],
            }
        ]
    if task["kind"] in {"aspect_analysis", "aspect_challenge"}:
        value.update(
            aspect_id=task["aspect_id"],
            applicability="undetermined",
            applicability_reason="Runtime and customer context absent",
            coverage="partial",
            outcome="undetermined",
            content=[
                {
                    "requirement_id": r,
                    "status": "unknown",
                    "answer": "Missing runtime and customer context",
                    "claim_ids": [],
                }
                for r in p["requirements"]
            ],
        )
        if task["kind"] == "aspect_challenge":
            value["analysis_verdict"] = "inconclusive"
    if task["kind"] in {"section_synthesis", "executive_synthesis"}:
        value["source_task_ids"] = [r["task_id"] for r in p["prior_results"]]
    if followup and p["available_followup_packets"] and value["claims"]:
        value["proposed_followups"] = [
            {
                "packet_id": p["available_followup_packets"][0]["packet_id"],
                "reason": "Check idempotency counterevidence",
                "evidence_refs": ["C1"],
            }
        ]
    return json.dumps(value)


def execute_round(ctx, ref, decision, model=fake):
    from handoff_test_support import review_task

    done = set()
    for node in decision["child_plan"]["steps"]:
        assert set(node["needs"]) <= done
        review_task(ctx, ref, {"id": node["id"], **node["input"]}, model)
        done.add(node["id"])


def test_hundreds_of_real_sdk_tasks_dynamic_and_complete_report(run):
    from domain.catalog_planning import planner, initializer
    from domain.catalog_publication import publish

    ctx, ref = run
    root = Path(ctx["run_dir"])
    seen = set()
    calls = []
    assert initializer(ctx)[0]["context"] == ref

    def model(prompt):
        calls.append(json.loads(prompt))
        assert len(prompt.encode()) <= ctx["config"]["catalog_review"]["prompt_bytes"]
        return fake(
            prompt, followup=json.loads(prompt)["task"]["kind"] == "aspect_challenge"
        )

    for rev in range(21):
        work = {"context": ref, "_child": {"revision": rev}}
        decision = planner(ctx, work)
        assert planner(ctx, work) == decision
        if decision["child_plan"]["decision"] == "stop":
            break
        batch = decision["child_plan"]["steps"]
        assert len(batch) <= 64
        ids = {n["id"] for n in batch}
        assert not ids & seen
        seen |= ids
        execute_round(ctx, ref, decision, model)
    else:
        pytest.fail("Did not stop within Core round ceiling")
    assert len(seen) > 324 and any(s.startswith("followup-") for s in seen)
    assert calls[-1]["task"]["kind"] == "executive_synthesis"
    analyses = [c for c in calls if c["task"]["kind"] == "aspect_analysis"]
    assert len(analyses) == 150
    challenges = [c for c in calls if c["task"]["kind"] == "aspect_challenge"]
    assert len(challenges) == 150
    assert all(c["prior_results"] for c in analyses + challenges)
    assert all(
        any(
            r["task_id"] == "analysis-" + c["task"]["aspect_id"]
            for r in c["prior_results"]
        )
        for c in challenges
    )
    ctx["output_folder"] = str(Path(ctx["run_dir"]).parent / "export")
    output, refs = publish(ctx)
    exported = Path(ctx["output_folder"])
    assert (exported / "report.md").is_file()
    assert (exported / "review_index.json").is_file()
    assert list((exported / "catalog/results").glob("*.json"))
    assert not list(exported.rglob("*.sqlite*"))
    assert output["status"] == "partial"
    assert len(json.dumps(output)) < 2000
    assert all((root / r["path"]).exists() for r in refs)
    coverage = json.loads((root / "coverage.json").read_text())
    assert len(coverage["aspects"]) == 150
    assert len(coverage["sections"]) == 23
    assert len(list((root / "sections").glob("*.md"))) == 23
    for name in [
        "claims",
        "findings",
        "recommendations",
        "assumptions",
        "verification_tasks",
        "roadmap",
        "work_packages",
        "evidence",
    ]:
        assert (root / (name + ".json")).exists()
    assert json.loads((root / "evidence.json").read_text())
    assert publish(ctx)[0] == output
    resultpath = next((root / "catalog/results").glob("*.json"))
    resultpath.write_text("{}")
    with pytest.raises(Exception):
        publish(ctx)


def test_unicode_packets_exact_and_path_inventory(run):
    from domain.review_packets import chunk_source
    from domain.catalog_contract import load_snapshot

    source = "🌍" * 25 + "\n" + "长" * 17 + "\r\nend"
    packets = chunk_source(
        "s", "src/你好 file.ts", source, hashlib.sha256(source.encode()).hexdigest(), 9
    )
    assert "".join(p["text"] for p in packets) == source
    assert all(
        len(p["text"].encode()) <= 9
        and source[p["start_offset"] : p["end_offset"]] == p["text"]
        for p in packets
    )
    with pytest.raises(ValueError):
        chunk_source("s", "x", source, "h", 1)
    ctx, _ = run
    root = Path(ctx["run_dir"])
    snap = load_snapshot(root)
    assert "src/module 0.py" in snap["inventory"]
    p = root / "evidence/snapshots/fixture/sources.json"
    v = json.loads(p.read_text())
    v["extra.py"] = next(iter(v.values()))
    p.write_text(json.dumps(v))
    with pytest.raises(ValueError, match="inventory"):
        load_snapshot(root)


def test_failed_call_budget_and_no_automatic_replay(run):
    from domain.catalog_planning import planner
    from domain.opencode_review import handle_task
    from domain.catalog_store import CatalogStore

    ctx, ref = run
    store = CatalogStore(ctx["run_dir"])
    plan = store.load_ref(store.load_ref(ref)["plan"])
    work = {"context": ref, "task": next(iter(plan["task_refs"].values()))}
    calls = []

    def invalid(prompt):
        calls.append(1)
        return "not json"

    first = handle_task(ctx, work, llm_client=invalid)
    assert first["status"] == "blocked"
    assert handle_task(ctx, work, llm_client=invalid) == first
    assert len(calls) == 1
    assert CatalogStore(ctx["run_dir"]).usage()["catalog_models"] == 1


def test_deadline_and_budget_publish_honest_unknowns(run, monkeypatch):
    from domain.catalog_planning import planner
    from domain.catalog_publication import publish
    from domain.catalog_store import CatalogStore

    ctx, ref = run
    store = CatalogStore(ctx["run_dir"])
    deadline = store.load_ref(ref)["deadline"]
    monkeypatch.setattr("domain.catalog_planning.time.time", lambda: deadline + 1)
    decision = planner(ctx, {"context": ref, "_child": {"revision": 0}})
    assert decision["child_plan"]["decision"] == "stop"
    publish(ctx)
    coverage = json.loads(Path(ctx["run_dir"], "coverage.json").read_text())
    assert all(
        r["coverage"] == "not_analyzed" and r["applicability"] == "undetermined"
        for r in coverage["aspects"]
    )


def test_citation_wrong_offsets_rejected(run):
    from domain.catalog_contract import load_snapshot
    from domain.review_response import citation

    ctx, _ = run
    s = load_snapshot(ctx["run_dir"])
    path = s["inventory"][0]
    source = s["sources"][path]
    c = {
        "path": path,
        "sha256": source["sha256"],
        "start_line": 1,
        "end_line": 1,
        "start_offset": 0,
        "end_offset": 3,
        "excerpt": "def",
    }
    assert citation(c, s) == c
    with pytest.raises(ValueError):
        citation({**c, "start_line": 2}, s)
    with pytest.raises(ValueError):
        citation({**c, "excerpt": "gateway"}, s)


def test_round_cannot_advance_before_prior_results(run):
    from domain.catalog_planning import planner

    ctx, ref = run
    planner(ctx, {"context": ref, "_child": {"revision": 0}})
    with pytest.raises(ValueError, match="unresolved"):
        planner(ctx, {"context": ref, "_child": {"revision": 1}})


def test_budget_reservation_survives_interruption(run):
    from domain.catalog_store import CatalogStore

    ctx, _ = run
    store = CatalogStore(ctx["run_dir"])
    assert store.reserve("task1", "digest", 1) == "reserved"
    assert store.reserve("task1", "digest", 1) == "interrupted"
    assert store.reserve("task2", "digest2", 1) == "exhausted"
    assert store.usage()["catalog_models"] == 1
    with pytest.raises(ValueError, match="changed"):
        store.reserve("task1", "different", 1)


def test_config_and_spec_hash_reject_mutation(run, tmp_path):
    from domain.catalog_planning import catalog_settings
    from domain.catalog_contract import load_catalog, bundled_specs_dir
    import shutil

    ctx, _ = run
    for key, value in [
        ("max_followups", 65),
        ("max_tasks", 1025),
        ("tasks_per_round", 65),
        ("max_rounds", 21),
    ]:
        cfg = json.loads(json.dumps(ctx["config"]))
        cfg["catalog_review"][key] = value
        with pytest.raises(ValueError):
            catalog_settings(cfg)
    copy = tmp_path / "report_specs"
    shutil.copytree(bundled_specs_dir(), copy)
    manifest = json.loads((copy / "manifest.json").read_text())
    path = copy / manifest["sections"][0]["specifications"][0]["path"]
    path.write_text("modified")
    with pytest.raises(ValueError, match="SHA-256"):
        load_catalog(copy)


def test_real_work_package_fields_trace_to_evidence_and_stay_proposed(run, monkeypatch):
    from domain.catalog_store import CatalogStore
    from domain.catalog_planning import planner
    from domain.opencode_review import handle_task
    from domain.catalog_publication import publish

    ctx, ref = run
    store = CatalogStore(ctx["run_dir"])
    saved = store.load_ref(ref)
    plan = store.load_ref(saved["plan"])
    taskref = plan["task_refs"]["analysis-AR-23-08"]

    def proposal(prompt):
        v = json.loads(fake(prompt))
        v["recommendations"] = [
            {
                "claim_ids": ["C1"],
                **{
                    k: "Verify payment retry behavior using a failure-injection fixture before changing the boundary."
                    for k in [
                        "action",
                        "alternatives",
                        "impact",
                        "effort",
                        "urgency",
                        "priority",
                        "prerequisites",
                        "risks",
                        "validation",
                        "success_conditions",
                        "next_decision",
                    ]
                },
            }
        ]
        v["work_packages"] = [
            {
                "claim_ids": ["C1"],
                "files": ["src/module 0.py"],
                **{
                    k: "Characterize duplicate charge behavior with a stub gateway and a bounded retry test."
                    for k in [
                        "goal",
                        "constraints",
                        "non_goals",
                        "migration_steps",
                        "required_tests",
                        "acceptance",
                        "stop_conditions",
                    ]
                },
            }
        ]
        return json.dumps(v)

    assert (
        handle_task(ctx, {"context": ref, "task": taskref}, llm_client=proposal)[
            "status"
        ]
        == "completed"
    )
    monkeypatch.setattr(
        "domain.catalog_planning.time.time", lambda: saved["deadline"] + 1
    )
    planner(ctx, {"context": ref, "_child": {"revision": 0}})
    publish(ctx)
    packages = store.read("work_packages.json")
    assert len(packages) == 1
    package = packages[0]
    assert package["approval_status"] == "not_authorized_by_report"
    assert (
        package["verification_required"]
        and package["evidence_ids"]
        and package["recommendation_ids"]
    )
    assert (store.root / "work_packages" / f"{package['id']}.md").is_file()


def test_model_choices_provider_settings_and_frozen_run(run):
    from domain.catalog_planning import catalog_settings, planner
    from domain.opencode_models import provider_config
    from domain.opencode_review import handle_task

    ctx, ref = run
    _, defaults = catalog_settings({})
    assert defaults["model"] == "opencode/muse-spark-1.3-contributor-free"
    assert provider_config(defaults) == {}
    for choice in ["Muse Glimmer 30BLocal Spark", "spark/muse-glimmer-30b"]:
        _, settings = catalog_settings({"opencode": {"model": choice}})
        assert settings["model"] == "spark/muse-glimmer-30b"
        provider = provider_config(settings)["provider"]["spark"]
        assert provider["options"]["baseURL"] == "http://10.0.4.32:8000/v1"
        assert provider["models"] == {"muse-glimmer-30b": {"name": "Muse Glimmer 30B"}}
    assert (
        catalog_settings({"opencode": {"model": "Muse Spark 1.3 FreeOpenCode Zen"}})[1]
        == defaults
    )
    for url in [
        "file:///v1",
        "http://user:secret@localhost/v1",
        "http://localhost/v1?key=secret",
    ]:
        with pytest.raises(ValueError, match="spark_base_url"):
            catalog_settings({"opencode": {"spark_base_url": url}})
    node = planner(ctx, {"context": ref, "_child": {"revision": 0}})["child_plan"][
        "steps"
    ][0]
    ctx["config"]["opencode"]["model"] = "spark/muse-glimmer-30b"
    with pytest.raises(ValueError, match="Frozen configuration changed"):
        handle_task(ctx, {"context": ref, **node["input"]}, llm_client=fake)


@pytest.mark.parametrize('response', ['not json', '[]', '{}', 'x' * 200001])
def test_immutable_review_blocks_invalid_model_response_and_continues(run, response):
    from domain.catalog_planning import planner
    from domain.catalog_store import CatalogStore
    from handoff_test_support import review_task
    ctx, ref = run
    decision = planner(ctx, {'context': ref, '_child': {'revision': 0}})
    first, second = decision['child_plan']['steps'][:2]
    assert first['label'].startswith('Scan source: ')
    calls = []
    def invalid(prompt):
        calls.append(prompt)
        return response
    review_task(ctx, ref, {'id': first['id'], **first['input']}, invalid)
    review_task(ctx, ref, {'id': first['id'], **first['input']}, invalid)
    store = CatalogStore(ctx['run_dir'])
    result = store.result(first['id'])
    assert result['status'] == 'blocked'
    assert result['claims'] == []
    assert len(calls) == 1
    review_task(ctx, ref, {'id': second['id'], **second['input']}, fake)
    assert store.result(second['id'])['status'] == 'completed'


def test_immutable_review_records_provider_failure_without_secret(run):
    from domain.catalog_planning import planner
    from domain.catalog_store import CatalogStore
    from handoff_test_support import review_task
    ctx, ref = run
    node = planner(ctx, {'context': ref, '_child': {'revision': 0}})['child_plan']['steps'][0]
    def unavailable(prompt):
        raise RuntimeError('private-provider-credential')
    review_task(ctx, ref, {'id': node['id'], **node['input']}, unavailable)
    result = CatalogStore(ctx['run_dir']).result(node['id'])
    assert result['status'] == 'blocked'
    assert 'private-provider-credential' not in json.dumps(result)


def test_immutable_review_input_integrity_failure_still_raises(run, monkeypatch):
    from domain.catalog_planning import planner
    from domain.sandbox_review import review_admitted
    ctx, ref = run
    node = planner(ctx, {'context': ref, '_child': {'revision': 0}})['child_plan']['steps'][0]
    def corrupted(reference):
        raise ValueError('artifact digest mismatch')
    monkeypatch.setattr('domain.sandbox_review.resolve_input', corrupted)
    with pytest.raises(ValueError, match='artifact digest mismatch'):
        review_admitted(node['input']['review_input'], llm_client=fake)
