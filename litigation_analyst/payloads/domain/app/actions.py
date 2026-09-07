"""Case-scoped actions and evidence policy for the planned investigation."""

from dataclasses import dataclass
from jsonschema import Draft202012Validator
from .planning import PLAN, OUTCOME, HYPOTHESIS, validate, check_citations
from .findings import submit_report, review_report
from .prompt_context import investigation_history


@dataclass
class InvestigationActions:
    cycle: object
    policy: dict
    runtime: object
    corpus: object
    data: dict
    store: object
    investigation_id: str

    def allowed_actions(self, state):
        execution = ["review_enquiry"]
        if self.runtime.read_hashes and self.cycle.state["actions"] < self.cycle.max_actions:
            execution.append("invoke_skill")
        planning = ["plan_enquiry", "submit_report"]
        if "report_review" in self.data:
            planning.append("finish")
        if self.policy["max_model_decisions"] - len(state["records"]) < 4:
            planning.remove("plan_enquiry")
            execution = ["review_enquiry"]
        return self.cycle.allowed_actions(planning=planning, execution=execution,
            common=("list_skills", "read_skill", "read_investigation", "flag_source", "update_hypothesis"),
            pending_review=("review_report",) if "pending_review_ids" in self.data else None)

    def __call__(self, action, state):
        cycle, policy, runtime, corpus = (
            self.cycle,
            self.policy,
            self.runtime,
            self.corpus,
        )
        data, store, investigation_id = self.data, self.store, self.investigation_id
        name, args = action["name"], action["arguments"]
        if "pending_review_ids" in data and name != "review_report":
            raise ValueError("review the pending finding before any further action")
        if name == "plan_enquiry":
            validate(PLAN, args)
            if policy["max_model_decisions"] - len(state["records"]) < 4:
                raise ValueError(
                    "finalization reserve reached; synthesize existing evidence"
                )
            cycle.start(dict(args))
            return {"plan": args, "phase": cycle.phase}
        if name == "review_enquiry":
            validate(OUTCOME, args)
            check_citations(args["evidence_ids"], store, investigation_id)
            args = {**args, "plan_index": len(cycle.state["plans"]) - 1}
            cycle.review(dict(args))
            return {"outcome": args, "phase": cycle.phase}
        if name == "read_investigation":
            if (
                set(args) != {"offset", "limit"}
                or type(args["offset"]) is not int
                or args["offset"] < 0
                or type(args["limit"]) is not int
                or not 1 <= args["limit"] <= 10
            ):
                raise ValueError(
                    "read_investigation requires offset >=0 and limit 1..10"
                )
            selected = state["records"][:-1][
                args["offset"] : args["offset"] + args["limit"]
            ]
            return {
                "records": investigation_history(selected),
                "next_offset": args["offset"] + len(selected),
                "total": len(state["records"]) - 1,
            }
        if name == "flag_source":
            if (
                set(args) != {"source_id", "reason"}
                or not isinstance(args["reason"], str)
                or not 1 <= len(args["reason"]) <= 1000
                or args["source_id"] not in {d.source_id for d in corpus.scan()}
            ):
                raise ValueError(
                    "flag_source requires an authorized source ID and bounded reason"
                )
            data["source_review_flags"][args["source_id"]] = args["reason"]
            return {"pending_human_review": args}
        if name == "submit_report":
            if cycle.phase != "planning":
                raise ValueError(
                    "review the active enquiry before submitting the report"
                )
            return submit_report(data, args, store, investigation_id)
        if name == "review_report":
            return review_report(data, args)

        if name == "list_skills":
            if args:
                raise ValueError("list_skills takes no arguments")
            return {"skills": runtime.list_skills()}
        if name == "read_skill":
            if set(args) != {"skill"}:
                raise ValueError("read_skill requires only skill")
            return runtime.read_skill(**args)
        if name == "invoke_skill":
            if set(args) != {"skill", "operation", "arguments"}:
                raise ValueError("invalid skill invocation fields")
            if policy["max_model_decisions"] - len(state["records"]) < 4:
                raise ValueError("finalization reserve reached; no further skill calls")
            cycle.require_execution()
            cycle.attempted()
            # Only this case's registered immutable operations are eligible for reuse.
            for record in state["records"][:-1]:
                previous = record["action"]
                if (
                    previous.get("name") == name
                    and previous.get("arguments") == args
                    and "result" in record
                    and "error" not in record["result"]
                ):
                    return {**record["result"], "reused": True}
            result = runtime.invoke_skill(**args)
            if "derivation" in result:
                data.setdefault("derivations", []).append(
                    {"arguments": args, "result": result}
                )
            return result
        if name == "update_hypothesis":
            Draft202012Validator(HYPOTHESIS).validate(args)
            evidence_ids = {e.evidence_id for e in store.evidence_for(investigation_id)}
            cited = set(args["supporting_evidence"] + args["contradictory_evidence"])
            if not cited <= evidence_ids:
                raise ValueError("hypothesis contains unverified evidence IDs")
            if args["status"] in ("supported", "contradicted") and not cited:
                raise ValueError(
                    "supported or contradicted hypotheses require source evidence"
                )
            if args["parent_id"] is not None and (
                args["parent_id"] not in data["hypotheses"]
                or args["parent_id"] == args["id"]
            ):
                raise ValueError("unknown or self-referencing parent hypothesis")
            data["hypotheses"][args["id"]] = dict(args)
            return {"hypothesis": args}
        if name == "finish":
            if (
                set(args) != {"reason"}
                or not isinstance(args["reason"], str)
                or not args["reason"].strip()
            ):
                raise ValueError("finish requires a reason")
            if "report_review" not in data:
                raise ValueError(
                    "submit and review the evidence-backed report before finishing"
                )
            if not data["hypotheses"]:
                raise ValueError(
                    "record at least one hypothesis and its limitations before finishing"
                )
            return {"reason": args["reason"]}
        raise ValueError("unknown investigation action")
