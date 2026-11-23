"""Plan review, parallel evidence work and evidence-led follow-ups through compiled workers."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_dynamic_rounds import RoundModel
from test_native_litigation_blocks import native_case


ORIGINAL = "Does the notice establish approval?"
UNCHANGED = "Which routine duties appear in the correspondence?"
EDITED = "Who approved the notice?"
ADDED = "Who signed the delivery register?"
FOLLOW_UP = "Does the register show who received the notice?"


class CaseModel(RoundModel):
    def completion_text(self, system, user):
        data = json.loads(user)
        stage = data["stage"]
        if stage == "search_design":
            self.calls.append(data)
            assert data["questions"] == {"H01": EDITED, "H03": ADDED}
            return json.dumps({"searches": [
                {"id": key, "support_query": term, "counter_query": "routine", "graph_tools": [],
                 "counsel_issue_ids": [], "expected_information": "Check the notice against the signed register."}
                for key, term in (("H01", "approval"), ("H03", "register"))]})
        result = json.loads(super().completion_text(system, user))
        if stage == "plan" and data["revision"] == 0:
            draft = result["hypotheses"][0]
            result["hypotheses"].append({**draft, "id": "H02", "question": UNCHANGED, "support_query": "duties"})
        if stage == "plan" and data["revision"] == 1:
            result["hypotheses"][0].update(id="H03", question=FOLLOW_UP, support_query="register",
                counter_query="receipt", expected_information="The register records dispatch. Receipt is still open.")
        if stage == "assess":
            enquiry = data["enquiry"]
            excerpt = data["evidence"][0]
            result["hypothesis"].update(id=enquiry["id"], question="Different model wording",
                factual_basis=excerpt["text"], assessment=excerpt["text"], supporting_evidence=[excerpt["evidence_id"]])
            result["report"]["findings"][0].update(assessment=excerpt["text"], evidence_ids=[excerpt["evidence_id"]])
        return json.dumps(result)


def draft(case, model):
    capture = case.execute("prepare_case_sources", {"input_folder": str(case.folder)})
    index = case.execute("build_case_indexes", {"previous": capture.outputs})
    scope = case.execute("scope_case_review", {"previous": index.outputs})
    return case.execute("draft_case_questions", {"previous": scope.outputs}, model=model)


def child_plan(case, seed, revision, model):
    child = {"revision": revision, "round": revision}
    return case.execute("plan_litigation_round", {"seed": seed, "_child": child},
                        template="plan_litigation_round", identity=f"round/{revision}", model=model).outputs["child_plan"]


def execute_branches(case, steps, revision, model):
    remaining = {step["id"]: step for step in steps}
    completed = set()
    with ThreadPoolExecutor(max_workers=6) as pool:
        while remaining:
            ready = [s for s in remaining.values() if set(s["needs"]) <= completed]
            assert ready, "Every unfinished branch must be reachable"
            futures = [pool.submit(case.execute, s["template"],
                {**s["input"], "_child": {"round": revision, "revision": revision}},
                template=s["template"], identity=f"{revision}/{s['id']}", model=model) for s in ready]
            for step, future in zip(ready, futures, strict=True):
                assert case.store.read(future.result().outputs["result"])
                completed.add(step["id"])
                del remaining[step["id"]]


@pytest.mark.parametrize("native_case", [{"text_memory": {"enabled": False}}, {}], indirect=True)
def test_reviewed_questions_and_discovered_lead_reach_the_cited_report(native_case, review_chat, monkeypatch):
    case, model = native_case, CaseModel()
    (case.folder / "register.txt").write_text("Morgan signed the delivery register at dispatch. Receipt is pending.")
    drafted = draft(case, model)
    assert not case.store.path("case/rounds/tasks").exists()
    assert not case.store.path("case/plan/execution.json").exists()
    assert [call["stage"] for call in model.calls] == ["plan"]

    def edit(record):
        assert record["metadata"]["default_answer"] == {"text": f"1. {ORIGINAL}\n2. {UNCHANGED}"}
        assert record["presentation"]["title"] == "Review investigation questions"
        assert ORIGINAL in record["presentation"]["text"] and UNCHANGED in record["presentation"]["text"]
        assert not case.store.path("case/rounds/tasks").exists()
        return {"option_id": "start", "text": f"2. {UNCHANGED}\n1. {EDITED}\n{ADDED}"}

    review_chat.answer = edit
    reviewed = case.execute("review_case_questions", {"previous": drafted.outputs})
    assert case.execute("review_case_questions", {"previous": drafted.outputs}) == reviewed
    assert review_chat.records[review_chat.waits[0]]["effect"] == "applied"
    seed = case.execute("investigate_case_evidence", {"previous": reviewed.outputs}, model=model).outputs["result"]
    first = child_plan(case, seed, 0, model)
    deps = {s["id"]: set(s["needs"]) for s in first["steps"]}
    assert len(deps) == 13
    for key in ["H02", "H01", "H03"]:
        assert not deps[key + "-evidence"] and not deps[key + "-counter"]
        assert deps[key + "-assessment"] == {key + "-evidence"}
        assert deps[key + "-review"] == {key + "-assessment", key + "-counter"}
    assert deps["summarize"] == {"H01-review", "H02-review", "H03-review"}
    execute_branches(case, first["steps"], 0, model)
    from domain import round_planning
    notify = round_planning.notify_followup
    def interrupted(*args):
        notify(*args)
        raise TimeoutError("Notice delivered before the planner received its reply")
    with monkeypatch.context() as patch:
        patch.setattr(round_planning, "notify_followup", interrupted)
        with pytest.raises(TimeoutError):
            child_plan(case, seed, 1, model)
    second = child_plan(case, seed, 1, model)
    assert [s["id"] for s in second["steps"]] == ["H04-evidence", "H04-counter", "H04-assessment", "H04-review", "summarize"]
    assert child_plan(case, seed, 1, model) == second
    notices = [r for r in review_chat.records.values() if r["kind"] == "notice"]
    assert len(notices) == 1 and not notices[0]["blocking"] and not notices[0]["options"]
    message = notices[0]["presentation"]["text"]
    assert FOLLOW_UP in message and ADDED in message and "Receipt is still open" in message
    assert len(review_chat.waits) == 1
    execute_branches(case, second["steps"], 1, model)
    terminal = child_plan(case, seed, 2, model)
    assert terminal["decision"] == "stop"
    case.execute("write_review_draft", {"previous": terminal["output"]})
    workspace = json.loads(case.store.path("case/workspace.json").read_text())
    questions = {q["question"]: q for q in workspace["issues"]}
    assert {q: row["origin"] for q, row in questions.items()} == {
        UNCHANGED: "Reviewed plan", EDITED: "Edited in Chat", ADDED: "Added in Chat", FOLLOW_UP: "Follow-up"}
    assert questions[FOLLOW_UP]["parent_id"] == questions[ADDED]["id"]
    assert all(q["assessment"] and q["supporting_evidence"] for q in questions.values())
    assert case.store.path("web/index.html").is_file()


def test_question_review_recovers_from_an_empty_reply_then_cancels(native_case, review_chat):
    case, model = native_case, CaseModel()
    drafted = draft(case, model)
    replies = iter([{"option_id": "start", "text": "1."}, {"option_id": "cancel", "text": "1."}])
    review_chat.answer = lambda _: next(replies)
    reviewed = case.execute("review_case_questions", {"previous": drafted.outputs})
    assert len(set(review_chat.waits)) == 2
    assert "Use distinct questions" in review_chat.records[review_chat.waits[-1]]["presentation"]["text"]
    seed = case.execute("investigate_case_evidence", {"previous": reviewed.outputs}, model=model).outputs["result"]
    terminal = child_plan(case, seed, 0, model)
    assert terminal["decision"] == "stop"
    assert case.store.read(terminal["output"]["result"])["stop_reason"] == "cancelled"
    assert not case.store.path("case/rounds/tasks").exists()
    assert [call["stage"] for call in model.calls] == ["plan"]


def test_follow_up_identity_respects_removed_and_reworded_questions():
    from domain.question_plan import followup_questions
    proposed = [{"id": "H01", "question": ORIGINAL}, {"id": "H02", "question": UNCHANGED}]
    previous = [{"hypotheses": [{"id": "H01", "question": EDITED, "origin": "Edited in Chat"}]}]
    candidates = [{"id": "H01", "question": q} for q in (ORIGINAL, UNCHANGED, FOLLOW_UP)]
    assert followup_questions(candidates, previous, {"H01": {}}, proposed) == [
        {"id": "H03", "question": FOLLOW_UP, "origin": "Follow-up", "parent_id": "H01"}]


@pytest.mark.parametrize("native_case", [{"workspace": {"authorized_source_ids": []}}], indirect=True)
def test_empty_authorized_scope_sends_no_case_questions(native_case, review_chat):
    case, model = native_case, CaseModel()
    drafted = draft(case, model)
    reviewed = case.execute("review_case_questions", {"previous": drafted.outputs})
    seed = case.execute("investigate_case_evidence", {"previous": reviewed.outputs}, model=model).outputs["result"]
    terminal = child_plan(case, seed, 0, model)
    assert case.store.read(terminal["output"]["result"])["stop_reason"] == "no_authorized_readable_sources"
    assert not model.calls and not review_chat.records
    assert not case.store.path("case/rounds/tasks").exists()
