"""Exercise real verifier hooks, frozen assignments and content-addressed handoffs across runs."""

import json
from hashlib import sha256

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_verification_checks_skill import make_plan
from software_verifier_suite.payloads.domain import delegation, specialist_workflow
from functional_verifier.payloads.domain import review
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import Mock

from block_workflow_fixture import run_sample

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name",
    [
        "software_verifier_suite",
        "functional_verifier",
        "compatibility_verifier",
        "security_verifier",
        "reliability_verifier",
        "gtm_planner",
        "gtm_executor",
    ],
)
def test_mailbox_is_in_compiled_stable_job(name):
    package = read_blueprint(ROOT / name)
    mcp = compile_blueprint(package).manifest["mcp"]
    declaration = mcp["mailbox"]
    assert declaration["delivery"] == "mailbox"
    assert declaration["sameRuntime"] is False
    if name == "software_verifier_suite":
        from mn_sdk.blueprints.definition import catalog_record
        from mn_sdk.blueprints.sources import normalize_blueprint

        catalog = normalize_blueprint(catalog_record(package, name))
        assert catalog["coworker_type"] == mcp["blueprint"]["coworker_type"] == "suite"
        assert len(catalog["collaboration"]["accepts"]) == 4
    if name == "software_verifier_suite" or name.endswith("_verifier"):
        assert declaration["managerBlueprintId"] == "software_verifier_suite"


@pytest.mark.parametrize("role", ["functional", "security", "reliability", "compatibility"])
def test_mailbox_only_specialist_with_an_empty_inbox(role, tmp_path, monkeypatch):
    from mn_sdk.blueprint.services import RunMailbox

    name = role + "_verifier"
    package = read_blueprint(ROOT / name)
    assert not package.document("contracts")["inputs"]["input_folder"]["required"]
    fields = {field["path"]: field for field in package.extension("mn.ui")["init_config_review"]["fields"]}
    assert fields["inputs.payload.input_folder"]["activeWhenAny"] == [
        {"key": "inputs.payload.collaboration_group_id", "equals": ""}
    ]
    mailbox = Mock()
    mailbox.next_assignment.return_value = None
    monkeypatch.setattr(RunMailbox, "open", lambda _: nullcontext(mailbox))
    config = {"inputs": {"payload": {"collaboration_group_id": "suite",
                                     "collaboration_peers": [{"jobId": "manager", "blueprintId": "software_verifier_suite"}]}}}
    result = run_sample(name, config=config, runs_root=tmp_path, wit_service=lambda op,args: {"items": []} if op == "mailbox.list" else pytest.fail(op))
    assert result["final_artifact"]["status"] == "waiting_for_assignment"
    assert result["final_artifact"]["checks"] == []
    assert "Waiting for an assignment" in (tmp_path / result["run_id"] / "report.md").read_text()
    mailbox.reply.assert_not_called()
    with pytest.raises((ValueError,RuntimeError), match="Choose a source folder"):
        run_sample(name, runs_root=tmp_path)


@pytest.fixture
def mailbox_office(tmp_path, monkeypatch, verifier_component_environment):
    def create(jobs):
        messages = {}
        runs = {}
        monkeypatch.setenv("MN_SHARED_STORAGE_ROOT", str(tmp_path))

        class Client:
            def __init__(self, **_options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def get_run(self, run):
                return json.dumps(runs[run])

            def job_mailbox(self, job, tool, args):
                if tool == "send_mailbox_message":
                    key = sha256((job + args["request_id"]).encode()).hexdigest()
                    row = {
                        **args,
                        "sender_job_id": job,
                        "sender_blueprint_id": jobs[job],
                        "id": key,
                        "status": "queued",
                    }
                    if row["kind"] == "result":
                        row["assignment_attachment"] = messages[row["reply_to"]][
                            "attachment"
                        ]
                    return messages.setdefault(key, row)
                if tool == "acknowledge_mailbox_message":
                    row = messages[args["message_id"]]
                    assert row["recipient_job_id"] == job
                    row["status"] = "acknowledged"
                    return row
                assert tool == "list_mailbox_messages"
                return {
                    "items": [
                        m
                        for m in messages.values()
                        if m["recipient_job_id"] == job
                        and (args.get("include_acknowledged") or m["status"] == "queued")
                        and m["kind"] == args["kind"]
                        and (not args.get("message_id") or m["id"] == args["message_id"])
                        and (not args.get("reply_to") or m["reply_to"] == args["reply_to"])
                    ][: args["limit"]],
                    "next_after": None,
                }

        monkeypatch.setattr("mn_sdk.integrations.run_mailbox.Client", Client)

        def block(job, run):
            ref = {"storage": "syncthing", "submission_id": job, "run_id": run}
            runs[run] = {"run_id": run, "job_id": job, "run_data_ref": ref}
            directory = tmp_path / "submissions" / job / "outputs/runs" / run
            directory.mkdir(parents=True)
            config = {
                "inputs": {
                    "payload": {
                        "collaboration_group_id": "suite",
                        "collaboration_peers": [
                            {"jobId": other, "blueprintId": role}
                            for other, role in jobs.items()
                            if job != other
                        ],
                    }
                }
            }
            return BlockContext(
                store=CommittedJsonStore(directory),
                invocation_id=run,
                revision="v1",
                job_id=job,
                run_id=run,
                config=config,
                environment={**verifier_component_environment(jobs[job]), "MN_JOB_ID": job, "MN_RUN_ID": run},
            )

        return block, messages
    return create


@pytest.mark.parametrize("late", [False, True], ids=["current-report", "later-review"])
def test_manager_delegates_only_matching_checks_and_validates_the_reply(
    tmp_path, monkeypatch, late, mailbox_office
):
    jobs = {
        "manager": "software_verifier_suite",
        "tester": "functional_verifier",
        "compat": "compatibility_verifier",
    }
    block, messages = mailbox_office(jobs)
    manager = block("manager", "manager-review")
    sources = {"test_name.py": "def test_name():\n    assert True\n"}
    plan = make_plan(sources, {}, run_id=manager.run_id)
    assigned = delegation.assign(manager, plan, sources, None)
    assert set(assigned) == {"functional"}
    assert delegation.assign(manager, plan, sources, None) == assigned
    assert all(row["recipient_job_id"] == "tester" for row in messages.values())
    assert delegation.collect(manager, plan, assigned) == ([], ["functional"])
    local = specialist_workflow._nodes(manager, {}, plan, 0, assigned)
    assert not set(assigned["functional"]["checks"]) & {
        node["input"]["assignment"].get("check_id") for node in local
    }
    specialist = block("tester", "specialist-review")
    packet = review.capture(specialist, {})
    result = review.inspect(specialist, {"previous": packet})
    assert result["data"]["final_artifact"]["verdict"] == "FAIL"
    assert sum(row["kind"] == "result" for row in messages.values()) == 1
    assert review.capture(specialist, {}) == packet
    if late:
        followup = block("manager", "next-review")
        reports = delegation.earlier_results(followup, {})
        assert len(reports) == 1
        assert (
            reports[0]["run_id"] == manager.run_id
            and reports[0]["report"]["verdict"] == "FAIL"
        )
        assert delegation.earlier_results(followup, {}) == reports
    else:
        records, pending = delegation.collect(manager, plan, assigned)
        assert not pending and {r["plan_id"] for r in records} == {plan["plan_id"]}
        assert specialist_workflow._rollup(manager, plan, records)["verdict"] == "FAIL"
    assert all(m["status"] == "acknowledged" for m in messages.values())


@pytest.mark.parametrize("connected", [[], ["functional_verifier"]])
def test_removed_specialists_are_not_run_locally(tmp_path, connected):
    config = {"inputs": {"payload": {
        "collaboration_group_id": "suite",
        "collaboration_peers": [{"jobId": role, "blueprintId": role} for role in connected],
    }}}
    block = BlockContext(store=CommittedJsonStore(tmp_path), invocation_id="review",
                         revision="v1", job_id="manager", run_id="review", config=config)
    sources = {"test_basic.py": "def test_feature():\n    assert True\n"}
    plan = make_plan(sources, {}, run_id="review")
    assert plan["checks"]
    absent = specialist_workflow.absent_roles(block)
    assert absent == {"functional", "security", "reliability", "compatibility"} - {
        name.removesuffix("_verifier") for name in connected
    }
    tasks = specialist_workflow._nodes(block, {}, plan, 0, {})
    assert {task["template"] for task in tasks} == ({"inspect_functional"} if connected else set())


def test_all_four_specialists_publish_a_single_evidence_report(mailbox_office, tmp_path, monkeypatch):
    import importlib
    from test_code_verifier import Model, phase_inputs
    from mn_sdk.blueprints import resolve_config
    from software_verifier_suite.payloads.domain.aspects import CATEGORIES
    from software_verifier_suite.payloads.domain import intake, rules, rule_review, verification, reporting

    package = read_blueprint(ROOT / "software_verifier_suite")
    sample = package.extension("mn.ui")["setup_guide"]["sample"]["values"]
    values = {
        key.removeprefix("inputs.payload."): (
            str(ROOT / "software_verifier_suite" / value[2:]) if value.startswith("@/") else value
        )
        for key, value in sample.items()
        if key.startswith("inputs.payload.")
    }
    jobs = {"coordinator": "software_verifier_suite", **{role: role + "_verifier" for role in CATEGORIES}}
    block, messages = mailbox_office(jobs)
    manager = block("coordinator", "dispatch-fixture")
    payload = {**values, **manager.config["inputs"]["payload"]}
    directory = tmp_path / "job"
    directory.mkdir()
    output = tmp_path / "published"
    manager.config = resolve_config(
        package, {"inputs": {"payload": payload}, "outputs": {"folder_path": str(output)}}
    ).data
    manager.original_config = manager.config
    manager.resources.update(job_data_dir=directory, output_folder=output)
    manager.environment.update(MN_JOB_DATA_DIR=str(directory), MN_JOB_OUTPUT_DIR=str(output))
    monkeypatch.setenv("MN_JOB_DATA_DIR", str(directory))
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(output))
    # The example exercises the production handoffs and publisher with a deterministic supervisor and static rule review.
    events = []
    monkeypatch.setattr(rule_review.human_interactions, "read_interaction_events", lambda *_: list(events))
    monkeypatch.setattr(
        rule_review.human_interactions,
        "publish_human_interaction_event",
        lambda _, kind, payload, **kw: events.append({"type": kind, "payload": payload}),
    )

    def approve(_, request_id, **kw):
        event = {
            "type": "human_input_received",
            "payload": {"request_id": request_id, "decision": "approve", "approved": True, "notes": ""},
        }
        events.append(event)
        return event

    monkeypatch.setattr(rule_review.human_interactions, "await_human_decision", approve)
    intake.capture(manager, payload)
    source = Path(values["input_folder"])
    # Supervision is scripted for this fictional fixture. Preserve one approval per declared passage.
    declared = []
    for line, statement in enumerate((source / "head/SPEC.md").read_text().splitlines()[2:], 3):
        declared.append({
            "statement": statement, "subject": "software", "scope": "product",
            "modality": "may" if " may " in statement else "must", "conditions": [],
            "requirement_kind": "behavior",
            "source_ids": [f"L{line}-" + sha256((statement + "\n").encode()).hexdigest()[:12]],
        })
    rules.extract(manager, phase_inputs(manager), llm=Model([{"complete": True, "rules": declared}]))
    approved = rule_review.review(manager, phase_inputs(manager))
    seed = specialist_workflow.initialize(manager, {"previous": approved})
    admission = manager.store.read(seed["packet"])
    assert set(admission["delegated"]) == set(CATEGORIES)
    for role, category in CATEGORIES.items():
        peer = block(role, role + "-dispatch")
        peer.environment["MN_MAILBOX_ASSIGNMENT_ID"] = admission["delegated"][role]["id"]
        handler = importlib.import_module(role + "_verifier.payloads.domain.review")
        packet = handler.capture(peer, {})
        result = handler.inspect(peer, {"previous": packet})["data"]["final_artifact"]
        assert result["aspect"]["cases"] and all(r["category"] == category for r in result["aspect"]["cases"])
    for revision in range(5):
        decision = specialist_workflow.plan_round(manager, {"seed": seed, "_child": {"revision": revision}})
        if decision["done"]:
            break
        for node in decision["tasks"]:
            getattr(specialist_workflow, node["template"])(
                manager, {"packet": admission, "assignment": node["input"]["assignment"]}
            )
    branch = specialist_workflow.summarize(manager, {"input": {"seed": seed}})
    assert all(m["status"] == "acknowledged" for m in messages.values())
    # The recorder ran no independent AI reviewer. The ordinary unavailable-model path keeps it unknown.
    verification.verify(manager, phase_inputs(manager), llm=Model([TimeoutError("No fixture source reviewer")] * 100))
    reporting.publish(manager, {**phase_inputs(manager), "specialists": branch})
    final = manager.store.read_path("final_artifact.json")
    a = final["assurance"]
    sections = {s["id"]: s for s in a["sections"]}
    assert list(sections) == ["functional", "defects", "compatibility", "security", "reliability"]
    assert {s["delivery"] for s in a["sections"] if s["id"] != "defects"} == {"received"}
    assert final["verdict"] == "FAIL" and a["decision_label"] == "Hold release"
    defects = {d["id"]: d for d in sections["defects"]["defects"]}
    assert set(defects) == {"DISPATCH-17"}
    assert defects["DISPATCH-17"]["distinct_runs"] == 2
    assert [p["id"] for p in sections["defects"]["policy_mismatches"]] == ["POLICY-04"]
    assert sections["defects"]["metrics"][1]["value"] == "1 / 1"
    assert len(sections["functional"]["requirements"]) == 7
    assert not sections["functional"]["unmapped"]
    assert {s["source_review"] for s in sections["functional"]["requirements"]} == {"unknown"}
    assert {g["kind"]: g["status"] for g in a["comparisons"]} == {
        "unit_tests": "passed", "lint": "passed", "ci": "unmeasured", "ai_review": "unmeasured",
    }
    assert sections["reliability"]["repairs"]["control-blank"]["status"] == "passed"
    assert {p["role"] for p in defects["DISPATCH-17"]["proofs"]} == {"functional", "compatibility"}
    assert sections["compatibility"]["metrics"][2]["value"] == "1"
    assert sections["reliability"]["metrics"][3]["value"] == "50%"
    assert all((output / f).is_file() for f in ["web/index.html", "report.md", "final_artifact.json"])
    assert all(s["title"] in (output / "report.md").read_text() for s in a["sections"])


def test_reply_window_collects_new_receipts_and_preserves_its_deadline(mailbox_office):
    block, messages = mailbox_office({"manager": "software_verifier_suite", "tester": "functional_verifier"})
    manager = block("manager", "wait-review")
    sources = {"test_local.py": "def test_value():\n    assert 1 == 1\n"}
    plan = make_plan(sources, {}, run_id=manager.run_id)
    assignments = delegation.assign(manager, plan, sources, None)
    now = [100.0]

    def run_specialist(delay):
        now[0] += delay
        peer = block("tester", "wait-peer")
        review.inspect(peer, {"previous": review.capture(peer, {})})

    records, pending, received = delegation.await_current(
        manager, plan, assignments, clock=lambda: now[0], sleep=run_specialist
    )
    assert records and not pending and set(received) == {"functional"}
    assert all(m["status"] == "acknowledged" for m in messages.values())
    # A late/resumed coarse poll checks the mailbox once and uses the originally frozen deadline.
    now[0] += 600
    other = {"functional": {**assignments["functional"], "id": "no-current-reply"}}
    assert delegation.await_current(
        manager, plan, other, clock=lambda: now[0], sleep=lambda _: pytest.fail("deadline reset")
    ) == ([], ["functional"], {})


def test_hired_specialist_uses_the_coordinators_pinned_runner_receipt(mailbox_office, tmp_path):
    block, _ = mailbox_office({"manager": "software_verifier_suite", "tester": "functional_verifier"})
    manager, peer = block("manager", "receipt-review"), block("tester", "receipt-peer")
    sources = {"workflow.txt": "A handoff completes."}
    from mn_verification_checks_skill import snapshot_id

    record = {
        "schema_version": "mn.verification.execution.v1",
        "check_id": "handoff",
        "subject": snapshot_id(sources),
        "base_commit": None,
        "revision": None,
        "artifact_sha256": None,
        "target": "local",
        "suite_sha256": "1" * 64,
        "runner_sha256": "2" * 64,
        "fixture_sha256": "3" * 64,
        "cases": {"handoff": ["passed"]},
    }
    raw = json.dumps(record, indent=2).encode()
    identity = sha256(raw).hexdigest()
    (tmp_path / (identity + ".json")).write_bytes(raw)
    scope = {
        "checks": [
            {
                "id": "handoff",
                "kind": "execution_record",
                "specialist": "functional",
                "requirement": "The handoff completes.",
                "target": "local",
                "suite_sha256": "1" * 64,
                "receipt_sha256": identity,
                "cases": ["handoff"],
            }
        ]
    }
    plan = make_plan(sources, scope, run_id=manager.run_id)
    delegated = delegation.assign(manager, plan, sources, None, evidence_folder=tmp_path)
    result = review.inspect(peer, {"previous": review.capture(peer, {})})["data"]["final_artifact"]
    assert result["checks"][0]["status"] == "passed"
    assert (peer.store.path("assigned-evidence") / (identity + ".json")).read_bytes() == raw
    returned, pending = delegation.collect(manager, plan, delegated)
    assert not pending and returned[0]["observations"] == {}
