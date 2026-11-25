"""Admission, attribution and counting rules that determine the public report's claims."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest
from mn_comparison_evidence_skill import assess, select
from software_verifier_suite.payloads.domain import assurance_basis, assurance_findings

EXAMPLE = Path(__file__).resolve().parents[1] / "software_verifier_suite" / "examples" / "dispatch_review"
UI = json.loads((EXAMPLE.parents[1] / "extensions/ui.json").read_text())["setup_guide"]["sample"]["values"]


def recorded(name):
    pin = UI["inputs.payload." + name]
    raw = (EXAMPLE / "evidence" / (pin + ".json")).read_bytes()
    assert sha256(raw).hexdigest() == pin
    return pin, json.loads(raw)


def example_sections():
    pin, ledger = recorded("assurance_evidence_sha256")
    ledger["digest"] = pin
    return {
        role: assess(select(ledger, category))
        for role, category in [
            ("functional", "workflow"),
            ("compatibility", "boundary"),
            ("security", "policy"),
            ("reliability", "test_control"),
        ]
    }


def test_case_links_respect_scope_approval_edits_and_ambiguous_passages():
    sections = example_sections()
    first = {
        "id": "retry",
        "statement": "Retries are idempotent.",
        "source": {"path": "pkg/SPEC.md", "start_line": 3, "end_line": 3},
    }
    current, gaps = assurance_findings.approved_requirements({"rules": [first]}, sections, "pkg/")
    assert current[0]["outcome"] == "unmet" and len(current[0]["cases"]) == 2
    assert all(row["case_id"] not in {"workflow-retry", "boundary-retry"} for row in gaps)
    edited = dict(first, review_edit={"statement_changed": True})
    current, gaps = assurance_findings.approved_requirements({"rules": [edited]}, sections, "pkg/")
    assert current[0]["outcome"] == "unmeasured" and not current[0]["cases"]
    assert any(row["reason"] == "Approved requirement changed" for row in gaps)
    current, gaps = assurance_findings.approved_requirements(
        {"rules": [first, dict(first, id="another")]}, sections, "pkg/"
    )
    assert all(r["outcome"] == "unmeasured" for r in current)
    assert any(row["reason"] == "Ambiguous passage" for row in gaps)
    current, _ = assurance_findings.approved_requirements({"rules": [first]}, sections, "different/")
    assert not current[0]["cases"]


def test_repeats_are_physical_runs_and_conflicting_views_remain_open():
    sections = example_sections()
    defects, policy, leads, repeats, attempted = assurance_findings.confirmed(sections)
    assert [(d["id"], d["distinct_runs"]) for d in defects] == [("DISPATCH-17", 2)]
    assert len(policy) == len(leads) == repeats == attempted == 1
    boundary = sections["compatibility"]["cases"][0]
    boundary["runs"][-1]["observed"] = "different recorded queue length"
    defects, policy, leads, repeats, attempted = assurance_findings.confirmed(sections)
    assert not defects and repeats == 0 and attempted == 1
    assert {"workflow-retry", "boundary-retry"} <= {p["case_id"] for p in leads}


def test_absent_specialists_contribute_no_corroboration():
    sections = example_sections()
    sections["compatibility"]["cases"] = []
    defects, _, _, _, _ = assurance_findings.confirmed(sections)
    assert len(defects[0]["proofs"]) == 1 and defects[0]["distinct_runs"] == 2
    sections["functional"]["cases"] = []
    defects, _, _, repeats, attempted = assurance_findings.confirmed(sections)
    assert not defects and (repeats, attempted) == (0, 0)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(subject="other-candidate"),
        lambda b: b.update(baseline_subject="other-baseline"),
        lambda b: b.update(case_digest="different-cases"),
        lambda b: b["gates"].update(lint="out-of-plan"),
        lambda b: b["gates"].update(lint=b["gates"]["unit_tests"]),
        lambda b: b["repair_checks"].update({"workflow-new": "existing-lint"}),
        lambda b: b["locations"]["workflow-new"][0].update(line=10000),
        lambda b: b["locations"]["workflow-new"][0].update(path="../outside"),
        lambda b: b.update(policy=["configuration"]),
    ],
)
def test_report_context_rejects_wrong_scope_or_unadmitted_claims(tmp_path, mutate):
    pin, original = recorded("assurance_basis_sha256")
    cases_pin, ledger = recorded("assurance_evidence_sha256")
    ledger["digest"] = cases_pin
    sources = {p.name: p.read_text() for p in (EXAMPLE / "comparison/head").iterdir() if p.is_file()}
    plan = {
        "subject": ledger["subject"],
        "baseline_subject": ledger["baseline_subject"],
        "paths": list(sources),
        "checks": [
            {"id": c, "kind": "execution_record"}
            for c in ("existing-lint", "existing-units", "blank-label-repair")
        ],
    }
    assert assurance_basis.read_basis(EXAMPLE / "evidence", pin, plan, ledger, sources)["origin"] == "fixture"
    assert assurance_basis.read_basis(None, "", plan, ledger, sources) == {}
    changed = deepcopy(original)
    mutate(changed)
    raw = json.dumps(changed).encode()
    key = sha256(raw).hexdigest()
    (tmp_path / (key + ".json")).write_bytes(raw)
    with pytest.raises(ValueError):
        assurance_basis.read_basis(tmp_path, key, plan, ledger, sources)


def test_missing_or_mismatched_runner_record_gives_no_gate_credit():
    plan = {
        "checks": [{"id": "units", "receipt_sha256": "pinned"}],
        "assurance_basis": {"gates": {"unit_tests": "units"}},
    }
    attempt = {
        "runner_sha256": "runner",
        "cases": {"test": ["passed"]},
        "evidence": [{"sha256": "different"}],
    }
    check = {"id": "units", "requirement": "Unit tests", "status": "passed", "attempts": [attempt]}
    report = {"specialist_report": {"plan": plan, "checks": [check]}}
    assert all(g["status"] == "unmeasured" for g in assurance_basis.comparisons(report))
    attempt["evidence"] = [{"sha256": "pinned"}]
    assert assurance_basis.comparisons(report)[0]["status"] == "passed"
    check["attempts"] = []
    assert assurance_basis.comparisons(report)[0]["status"] == "unmeasured"


def test_mapped_junit_never_grants_a_whole_pipeline_pass():
    report = {
        "specialist_report": {"checks": [], "plan": {}},
        "ci_evidence": {
            "checks": [
                {"mapping": "linked", "status": "passed"},
                {"mapping": "rule_edited", "status": "failed"},
            ]
        },
    }
    gate = next(g for g in assurance_basis.comparisons(report) if g["kind"] == "ci")
    assert gate["status"] == "partial"
    assert "1 passed" in gate["detail"] and "unmeasured" in gate["detail"]


def test_unrelated_cases_can_reuse_local_run_names():
    sections = example_sections()
    boundary = sections["compatibility"]["cases"][0]
    boundary["issue"] = "independent-review"
    for run in boundary["runs"]:
        if run["revision"] == "candidate":
            run["observed"] = "another outcome"
    defects, _, _, reproduced, attempted = assurance_findings.confirmed(sections)
    assert {d["id"] for d in defects} == {"DISPATCH-17", "independent-review"}
    assert reproduced == attempted == 2
