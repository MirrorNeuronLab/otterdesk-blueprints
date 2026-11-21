"""Exercise real verifier hooks, frozen assignments and content-addressed handoffs across runs."""

import json
from hashlib import sha256

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_verification_checks_skill import make_plan
from code_verifier.payloads.domain import delegation, specialist_workflow
from functional_verifier.payloads.domain import review
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import Mock

from block_workflow_fixture import run_sample

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name",
    [
        "code_verifier",
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
    declaration = compile_blueprint(package).manifest["mcp"]["mailbox"]
    assert declaration["delivery"] == "mailbox" and declaration["sameRuntime"]
    if name.endswith("_verifier"):
        assert declaration["managerBlueprintId"] == "code_verifier"


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
                                     "collaboration_peers": [{"jobId": "manager", "blueprintId": "code_verifier"}]}}}
    result = run_sample(name, config=config, runs_root=tmp_path)
    assert result["final_artifact"]["status"] == "waiting_for_assignment"
    assert result["final_artifact"]["checks"] == []
    assert "Waiting for an assignment" in (tmp_path / result["run_id"] / "report.md").read_text()
    mailbox.reply.assert_not_called()
    with pytest.raises(ValueError, match="Choose a source folder"):
        run_sample(name, runs_root=tmp_path)


@pytest.mark.parametrize("late", [False, True], ids=["current-report", "later-review"])
def test_manager_delegates_only_matching_checks_and_validates_the_reply(
    tmp_path, monkeypatch, late
):
    messages = {}
    jobs = {
        "manager": "code_verifier",
        "tester": "functional_verifier",
        "compat": "compatibility_verifier",
    }
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
            environment={"MN_JOB_ID": job, "MN_RUN_ID": run},
        )

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
