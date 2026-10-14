import io
import json

from PIL import Image
from cctv_operator.payloads.domain.benchmarks import Benchmarks
from cctv_operator.payloads.domain.person_events import PersonEpisodes
from cctv_operator.payloads.domain.person_evidence import PersonEvidence


def test_confirmed_person_episode_emits_standard_finding_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MN_AGENT_ID", "adaptive_frame_sampler")
    monkeypatch.setenv("MN_WORKFLOW_STEP_ID", "adaptively_sample_video")
    episodes = PersonEpisodes({})
    person = {"label": "person", "confidence": .9, "xyxy": [1, 2, 30, 40]}
    assert episodes.update([person], 10) is None
    confirmed = episodes.update([person], 10.2)
    stream = io.BytesIO()
    Image.new("RGB", (96, 54)).save(stream, "JPEG")
    evidence = PersonEvidence(tmp_path, "run", {}, Benchmarks(tmp_path))
    evidence.record(confirmed, stream.getvalue(), {}, "RF-DETR")
    assert episodes.update([person], 10.4) is None
    records = [json.loads(line.removeprefix("__MN_EVENT__")) for line in capsys.readouterr().out.splitlines()]
    assert len(records) == 1
    record = records[0]
    assert record["schema"] == "mn.runtime.event.v1"
    assert record["payload"]["message"] == "Person presence confirmed"
    assert record["owner_blueprint"] == "cctv_operator"
    assert record["activity_kind"] == "finding"
    assert record["payload"]["details"]["episode"] == confirmed["episode"]
    assert record["payload"]["details"]["confidence"] == .9
    assert "helmet" not in record["payload"]["message"]


def test_resident_lane_reports_work_confirmation_and_observed_absence_without_frame_spam(tmp_path, monkeypatch, capsys):
    from cctv_operator.payloads.domain.live_monitor import LiveMonitor
    monkeypatch.setenv("MN_AGENT_ID", "resident_monitor")
    stream = io.BytesIO()
    Image.new("RGB", (96, 54)).save(stream, "JPEG")
    content = stream.getvalue()
    people = [{"label": "person", "confidence": .9, "xyxy": [1, 2, 30, 40]}]
    class Source:
        index = 0
        def latest_frame(self):
            self.index += 1
            return self.index, [100, 100.2, 100.4, 101, 102.5][self.index - 1], content
    class Detector:
        variant = "RF-DETR"
        metadata = {}
        index = 0
        def load(self):
            pass
        def detect(self, _jpeg):
            self.index += 1
            return people if self.index < 3 else []
    class Stop:
        count = 0
        def is_set(self):
            return self.count >= 5
        def wait(self, _seconds):
            self.count += 1
    monitor = LiveMonitor(tmp_path, "run", {}, Source(), None, detector=Detector())
    monitor.stop_event = Stop()
    monitor._person_loop()
    records = [json.loads(line.removeprefix("__MN_EVENT__")) for line in capsys.readouterr().out.splitlines()]
    assert [record["payload"]["message"] for record in records] == [
        "Checking frames for people", "Person presence confirmed",
        "No person detected in sampled frames for 2 seconds",
    ]
    assert records[-1]["payload"]["details"]["qualification"] == "sampled_scene_absence_not_identity"
    assert all(record["owner_blueprint"] == "cctv_operator" for record in records)
