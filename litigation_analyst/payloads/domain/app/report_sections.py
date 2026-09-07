"""Evidence-only summaries and graph exhibits for a human investigation reviewer."""

import json
import re


def graph_exhibits(records):
    lines = [
        "## Graph examinations",
        "",
        "These are recorded results from MN Graph Engine (Rust), not findings of culpability. Graph associations require corroboration from source passages.",
        "",
    ]
    completed = [
        r
        for r in records
        if r.get("result", {}).get("provenance") == "observed_graph_query"
        and not r.get("result", {}).get("reused")
    ]
    if not completed:
        lines += ["No successful graph examination was recorded.", ""]
    for number, record in enumerate(completed, 1):
        args = record["action"]["arguments"]["arguments"]
        result = record["result"]["result"]
        lines += [
            f"### Graph exhibit G{number}",
            "",
            "Query and returned data are quoted verbatim as JSON from the action audit:",
            "",
        ]
        # A fence longer than any run in untrusted JSON prevents fence breakout.
        text = json.dumps(
            {"query": args, "result": result}, ensure_ascii=False, indent=2
        )
        fence = "`" * max(
            3, max((len(part) for part in re.findall(r"`+", text)), default=0) + 1
        )
        lines += [
            fence + "json",
            text,
            fence,
            "",
            "Source: `case/agent_checkpoint.json`, completed graph action in recorded order.",
            "",
        ]
    return lines


def examination_summary(evidence, hypotheses, records, stop_reason):
    graph_count = sum(
        r.get("result", {}).get("provenance") == "observed_graph_query"
        and not r.get("result", {}).get("reused")
        for r in records
    )
    return [
        "# Investigation Report",
        "",
        "**Status: Final workflow output — draft for human review.**",
        "",
        "## Executive summary",
        "",
        f"The recorded investigation retained {len(evidence)} exact source passages, {graph_count} successful graph examinations, and {len(hypotheses)} structured hypotheses.",
        f"Execution stopped because: `{stop_reason}`.",
        "This report contains no independently established allegation of wrongdoing. Source statements are quotations, not independently verified assertions of truth.",
        "",
        "## Scope and authority",
        "",
        "Examination was limited to the authorized frozen corpus. No external acquisition, interviews, communications, or legal actions were performed.",
        "",
    ]
