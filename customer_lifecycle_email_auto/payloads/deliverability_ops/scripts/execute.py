#!/usr/bin/env python3
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _synaptic_runtime.core import load_input_plan, log_agent


AGENT_ID = "deliverability_ops_agent"


def main() -> None:
    plan = load_input_plan()
    customer = plan["customer"]
    runtime_job_id = plan.get("runtime_job_id")

    reasons = []
    violated_rules = []

    if not customer.get("email"):
        violated_rules.append("missing_email")
        reasons.append("Customer record does not have an email address.")

    if customer.get("suppression_status") != "active":
        violated_rules.append("suppression_status_block")
        reasons.append(
            f"Suppression status is '{customer.get('suppression_status')}', so outreach is blocked."
        )

    if customer.get("opt_in_status") in {"unsubscribed", "opted_out"}:
        violated_rules.append("opt_out_block")
        reasons.append("Customer is opted out from email outreach.")

    plan["policy_decision"] = {
        "decision": "block" if violated_rules else "allow",
        "reasons": reasons if violated_rules else ["Customer is active and subscribed."],
        "violated_rules": violated_rules,
        "approval_requirements": [],
    }

    log_agent(
        runtime_job_id,
        AGENT_ID,
        "Completed deliverability review.",
        details={"decision": plan["policy_decision"]["decision"]},
    )
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
