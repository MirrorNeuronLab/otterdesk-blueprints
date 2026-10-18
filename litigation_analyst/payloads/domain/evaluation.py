"""Offline acceptance: mechanical provenance checks and attributable human judgment."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .matter_intake import valid_timestamp


def evaluate(root, expected_path, human_path=None):
    root = Path(root).resolve()
    expected_path = Path(expected_path).resolve()
    if root == expected_path or root in expected_path.parents:
        raise ValueError("Keep the answer key outside the run and case inputs")
    expected = json.loads(expected_path.read_text())
    workspace = json.loads((root / "case/workspace.json").read_text())
    sources = {s["source_id"]: s for s in json.loads((root / "case/sources.json").read_text())}
    errors = []
    evidence = {e["evidence_id"]: e for e in workspace["evidence"]}
    for item in evidence.values():
        source = sources.get(item["source_id"])
        text = source.get("text") if source else None
        if (text is None or hashlib.sha256(text.encode()).hexdigest() != item["content_sha256"]
                or not 0 <= item["start_offset"] < item["end_offset"] <= len(text)
                or text[item["start_offset"]:item["end_offset"]] != item["text"]):
            errors.append("Invalid exact passage: " + item["evidence_id"])
    financial = workspace.get("financial_review", {})
    amounts = {}
    kinds = {"requested": "requested_usd", "approved": "written_approval_usd",
             "posting": "posted_usd", "reversal": "reversed_usd"}
    for kind, name in kinds.items():
        rows = [r for r in financial.get("events", []) if r["currency"] == "USD" and r["event_type"] == kind]
        if len(rows) == 1:
            amounts[name] = abs(Decimal(rows[0]["amount"]))
    transactions = financial.get("transactions", [])
    if len(transactions) == 1 and transactions[0]["currency"] == "USD":
        for key, field in (("difference_usd", "request_minus_approval"), ("ledger_net_usd", "posting_reversal_net")):
            if transactions[0][field] is not None:
                amounts[key] = Decimal(transactions[0][field])
    comparisons = {name: {"expected": str(value), "observed": str(amounts.get(name)),
                         "matches": amounts.get(name) == Decimal(str(value))}
                   for name, value in expected.get("must_distinguish", {}).items()}
    sentinel = expected.get("privileged_sentinel_must_not_appear_in_findings")
    if sentinel and sentinel in json.dumps(workspace, ensure_ascii=False):
        errors.append("Excluded content leaked into published workspace")
    required = [*expected.get("required_qualifications", []), *expected.get("counterevidence", []), *expected.get("gaps", [])]
    human_status = "pending_attorney_review"
    if human_path:
        human = json.loads(Path(human_path).read_text())
        if (not isinstance(human.get("reviewer"), str) or not human["reviewer"].strip()
                or not valid_timestamp(human.get("reviewed_at"))):
            raise ValueError("Human review requires named reviewer and ISO reviewed_at")
        if human.get("snapshot_id") != workspace["snapshot_id"]:
            raise ValueError("Human review must bind this exact workspace snapshot")
        reviews = human.get("finding_reviews", [])
        findings = {f["id"]: f for f in workspace["findings"]}
        if len(reviews) != len(findings) or {r["finding_id"] for r in reviews} != set(findings):
            raise ValueError("Review every published finding once")
        for row in reviews:
            basis = set(findings[row["finding_id"]]["supporting_evidence"] + findings[row["finding_id"]]["counter_evidence"])
            if not row.get("rationale", "").strip() or not row.get("evidence_ids") or not set(row["evidence_ids"]) <= basis:
                raise ValueError("Each human finding review needs rationale and exact source basis")
        criteria = human.get("criteria", [])
        if len(criteria) != len(required) or {r["criterion"] for r in criteria} != set(required):
            raise ValueError("Review every expected qualification, counterevidence and gap once")
        passing = (all(r.get("supported") is True for r in reviews)
                   and all(r.get("retained") is True and r.get("rationale", "").strip() for r in criteria)
                   and human.get("unsupported_material_allegations") == 0)
        human_status = "attorney_attested_pass" if passing else "attorney_attested_fail"
    mechanical = not errors and all(c["matches"] for c in comparisons.values())
    return {"snapshot_id": workspace["snapshot_id"], "provenance_errors": errors,
            "typed_financial_comparisons": comparisons, "mechanical_checks_pass": mechanical,
            "human_review": human_status, "acceptance": "passed" if mechanical and human_status == "attorney_attested_pass" else "failed" if not mechanical or human_status == "attorney_attested_fail" else "pending_attorney_review",
            "qualification": "Exact spans and typed arithmetic do not prove narrative accuracy, source truth or legal correctness. Human annotations are self-attributed, not authenticated. No keyword scoring."}
