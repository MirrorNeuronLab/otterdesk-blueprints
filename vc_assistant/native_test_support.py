"""Offline owner fixture for native-worker tests; never shipped in payloads.

Core's actual admission/persistence transitions are verified in its own suite.
This transport fixture persists a synthetic owner across independent CLI workers.
"""

import json
import sqlite3
from types import SimpleNamespace


class WorkflowBudgetOwner:
    def __init__(self, path):
        self.path = str(path)
        self.channel = SimpleNamespace(close=lambda: None)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("CREATE TABLE IF NOT EXISTS budgets (identity TEXT PRIMARY KEY, state TEXT NOT NULL)")

    def set_resource(self, request):
        identity = json.dumps([request[key] for key in ("job_id", "run_id", "name")])
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            saved = db.execute("SELECT state FROM budgets WHERE identity=?", (identity,)).fetchone()
            state = json.loads(saved[0]) if saved else {"limit": request["limit"], "used": 0, "actions": {}}
            if state["limit"] != request["limit"]:
                raise RuntimeError("Synthetic owner allowance changed")
            if request["action"] == "start":
                fields = {key: request[key] for key in ("action_type", "stage", "entity_id", "tool", "scope", "revision", "metadata")}
                identifier = request["request_id"]
                record = state["actions"].get(identifier)
                if record:
                    if record["request"] != fields:
                        raise RuntimeError("Synthetic owner request changed")
                else:
                    cost = int(state["used"] < state["limit"])
                    state["used"] += cost
                    action = {**fields, "reservation_id": identifier,
                        "action_index": len(state["actions"]) + 1, "cost": cost,
                        "budget": state["limit"], "used": state["used"],
                        "remaining": state["limit"] - state["used"],
                        "status": "started" if cost else "budget_exhausted",
                        "recorded_at": "2026-01-01T00:00:00Z"}
                    record = {"request": fields, "action": action}
                    state["actions"][identifier] = record
                result = {"status": "admitted" if record["action"]["cost"] else "budget_exhausted",
                    "action": record["action"], "request": record["request"], "budget": state["limit"], "used": state["used"]}
            elif request["action"] == "complete":
                record = state["actions"][request["request_id"]]
                if (record["request"]["scope"] != request["scope"]
                    or record["request"]["revision"] != request["revision"] or record["action"]["cost"] != 1):
                    raise RuntimeError("Synthetic owner completion belongs to another scope")
                completion = {key: request[key] for key in ("status", "metadata")}
                if "completion" in record and record["completion"] != completion:
                    raise RuntimeError("Synthetic owner completion changed")
                record["completion"] = completion
                record["action"].update(status=request["status"], completed_at="2026-01-01T00:00:01Z",
                    metadata={**record["action"]["metadata"], **request["metadata"]})
                result = {"status": "completed", "request_id": request["request_id"], "scope": request["scope"]}
            elif request["action"] == "summary":
                result = {"budget": state["limit"], "used": state["used"],
                    "remaining": state["limit"] - state["used"], "exhausted": state["used"] >= state["limit"],
                    "actions": sorted((item["action"] for item in state["actions"].values()), key=lambda item: item["action_index"])}
            else:
                raise RuntimeError("Unknown synthetic owner operation")
            db.execute("INSERT OR REPLACE INTO budgets(identity,state) VALUES (?,?)", (identity, json.dumps(state)))
        return json.dumps({"schema": "mn.workflow_budget/v1", "name": request["name"], "run_id": request["run_id"], "job_id": request["job_id"], **result})
