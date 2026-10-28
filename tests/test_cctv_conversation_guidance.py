"""Blueprint guidance reaches the installed conversation and domain replies."""

import importlib
from pathlib import Path

import pytest
from mn_sdk.blueprints import blueprint_definition, catalog_record, read_blueprint
from mn_sdk_job_response.agent_memory import AgentMemory
from mn_sdk_job_response.agent_planner import AgentPlanner
from mn_sdk_job_response.agent_store import AgentStore


ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


def test_setup_publishes_safe_help_and_a_resolvable_ai_prompt(tmp_path):
    package = read_blueprint(ROOT)
    metadata = catalog_record(package, "cctv_operator")
    guide = metadata["setup_guide"]
    for fields in (guide["fields"], metadata["init_config_review"]["fields"]):
        field = next(item for item in fields if item["path"] == "video_source.uri")
        assert field["label"] == "Video stream URL"
        assert f"{field['label']}: Saved securely" == "Video stream URL: Saved securely"
        assert field["secret"] is True and field["type"] == "password"
        assert field["required"] is True and not field.get("default")
    assert guide["sample"]["available"] is False
    assert "progress panel" in guide["introduction"]
    prompt_path = ROOT / guide["prompt_file"].removeprefix("@/")
    assert prompt_path.is_relative_to(ROOT / "payloads/prompts")
    prompt = prompt_path.read_text()
    assert 0 < len(prompt_path.read_bytes()) <= 12000
    assert "Video stream URL" in prompt and "secure" in prompt

    # The active Job planner consumes the installed manual, not the standalone
    # visual prompt or a document that merely happens to exist in the bundle.
    declaration = blueprint_definition(package)["response_service"]["agent"]
    store = AgentStore(tmp_path / "conversation.sqlite3", "guidance-test")
    memory = AgentMemory(declaration=declaration, store=store,
                         job_data_dir=tmp_path, rag_refresh=lambda: None)
    system = AgentPlanner(declaration=declaration, store=store, memory=memory).system_prompt()
    manual = (ROOT / "knowledge/user_manual.md").read_text()
    assert manual in system
    assert "## Connect your camera" in system
    assert "'artifact_id':" not in manual


@pytest.mark.parametrize("preview,next_action", [
    ("live", "Follow startup"),
    ("connecting", "Follow startup"),
    ("unavailable", "Check that the NVIDIA computer can reach"),
])
def test_no_analysis_explains_stage_and_next_action(monkeypatch, preview, next_action):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    status = importlib.import_module("domain.conversation_status")
    summary = status.operator_status_summary({
        "metrics": {"preview": preview, "last analyzed": "waiting", "frames analyzed": 0},
        "pipeline": {"person_events": {"summary": "Person detection is ready. Waiting for a video frame."},
                     "captions": {"summary": "Scene analysis in progress (20 s)."}},
    })
    assert summary.startswith("I don't have a completed scene analysis yet.")
    assert "\n\n- Camera:" in summary
    assert "Scene analysis in progress (20 s)" in summary
    assert next_action in summary
    assert "Last analyzed: waiting" not in summary


def test_failed_analysis_keeps_last_sample_separate_from_current_health(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    status = importlib.import_module("domain.conversation_status")
    summary = status.operator_status_summary({
        "metrics": {"preview": "live", "status": "Analysis error", "frames analyzed": 1,
                    "latest finding": "A cart was beside the aisle.", "last analyzed": "2026-10-27T13:00:00Z"},
        "understanding": {"source_profile": "bundled_demo"},
        "warning": "Scene processing failed.",
    })
    assert "Latest analyzed sample at 2026-10-27T13:00:00Z" in summary
    assert "A cart was beside the aisle." in summary
    assert "Scene processing failed." in summary
    assert "Recorded demo playback" in summary and "not a live site event" in summary
    assert "Check scene-analysis status" in summary
    assert "does not mean the scene is clear" in summary


def test_latest_status_retains_detailed_activity_instead_of_the_short_metric(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    status = importlib.import_module("domain.conversation_status")
    account = ("In frames 1–3, the person in blue lifts a box with both hands and turns toward the aisle. "
               "In frames 4–6, they carry it to the table on the right and set it down. "
               "The second person's hands remain occluded, so their task cannot be determined.")
    summary = status.operator_status_summary({"metrics": {"preview": "live", "latest finding": "Two people visible.",
        "last analyzed": "2026-10-27T20:00:00Z"}, "understanding": {"scene_understanding": account}})
    assert account in summary
    assert "2026-10-27T20:00:00Z" in summary
    assert "Two people visible." not in summary


def test_goal_summaries_distinguish_queued_applied_and_analyzed(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    status = importlib.import_module("domain.conversation_status")
    pending = status.monitoring_command_summary("accepted", instruction="Watch the corridor")
    assert "not been confirmed as applied" in pending
    applied = status.monitoring_command_summary("completed", instruction="Watch the corridor",
        finding="An old-goal finding", analysis_ready=False)
    assert "The monitoring goal is now: Watch the corridor" in applied
    assert "not available yet" in applied and "An old-goal finding" not in applied
    analyzed = status.monitoring_command_summary("completed", instruction="Watch the corridor",
        finding="A cart blocks the corridor", analysis_ready=True)
    assert "A cart blocks the corridor" in analyzed
    restored = status.monitoring_command_summary("completed", clear=True)
    assert "configured monitoring goal has been restored" in restored
    assert "not available yet" in restored


@pytest.mark.parametrize("history_status,next_action", [
    ("no_evidence", "Check monitoring status"),
    ("disabled", "Enable context memory"),
    ("insufficient_capacity", "Choose a shorter time interval"),
    ("unavailable", "then try again"),
])
def test_empty_history_has_actionable_guidance_without_a_model_call(monkeypatch, tmp_path, history_status, next_action):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    history = importlib.import_module("domain.video_questions")
    monkeypatch.setattr(history, "read_video_history", lambda *args, **kwargs: {
        "history": {"status": history_status, "evidence": []},
        "qualification": "Sampled history, not continuous coverage.",
    })
    def unexpected_model(*args, **kwargs):
        pytest.fail("An empty history answer must not invoke a model")
    monkeypatch.setattr(history, "completion_json", unexpected_model)
    reply = history.answer_video({}, tmp_path, "test-run", "What happened?")
    assert next_action in reply["summary"]
    assert reply["citations"] == []
    assert reply["continuous_coverage"] is False
    assert reply["summary"].endswith("\n\nSampled history, not continuous coverage.")
