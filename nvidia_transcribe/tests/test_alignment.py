"""Measured evidence, unknown speakers, and invalid timestamp boundaries."""

import copy
import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def alignment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "payloads"))
    for name in list(sys.modules):
        if name == "domain" or name.startswith("domain."):
            monkeypatch.delitem(sys.modules, name)
    return importlib.import_module("domain.alignment")


def response():
    return {
        "ctc_timestamps": {
            "error": None,
            "words": [
                {"word": "Hello", "start": 0.1, "end": 0.5, "speaker": "<spk:0>"},
                {"word": "there.", "start": 0.4, "end": 0.8, "speaker": "<spk:1>"},
            ],
            "diarization": [
                {"start": 0.1, "end": 0.6, "speaker": 2},
                {"start": 0.4, "end": 0.8, "speaker": 5},
            ],
            "speaker_tag_to_diarization_speaker": {"<spk:0>": 2, "<spk:1>": 5},
        }
    }


def test_measured_words_use_the_diarizer_mapping_and_preserve_overlap(alignment):
    result = alignment.playback_alignment(response(), "<spk:0>Hello <spk:1>there.", 1)
    assert result["status"] == "ready"
    assert result["speakers"] == ["2", "5"]
    assert result["words"][0]["speaker"] == "2"
    assert result["words"][1]["start"] < result["words"][0]["end"]


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, -1, 5])
def test_invalid_times_never_create_a_playable_report(alignment, value):
    raw = response()
    raw["ctc_timestamps"]["words"][0]["start"] = value
    assert alignment.playback_alignment(raw, "Hello there.", 1) == {
        "status": "unavailable"
    }


def test_missing_unknown_and_empty_are_distinct(alignment):
    assert alignment.playback_alignment({}, "Hello", 1)["status"] == "unavailable"
    raw = response()
    raw["ctc_timestamps"]["speaker_tag_to_diarization_speaker"] = {}
    raw["ctc_timestamps"]["diarization"] = []
    result = alignment.playback_alignment(raw, "Hello there.", 1)
    assert result["speakers"] == []
    assert all(word["speaker"] is None for word in result["words"])
    raw["ctc_timestamps"]["speaker_tag_to_diarization_speaker"] = {"<spk:0>": None}
    assert (
        alignment.playback_alignment(raw, "Hello there.", 1)["words"][0]["speaker"]
        is None
    )
    raw["ctc_timestamps"]["words"] = []
    assert alignment.playback_alignment(raw, "", 1)["status"] == "ready"
    assert alignment.playback_alignment(raw, "Lost text", 1)["status"] == "unavailable"


def test_partial_alignment_is_not_presented_as_complete(alignment):
    raw = response()
    assert (
        alignment.playback_alignment(raw, "Hello there. More words.", 1)["status"]
        == "unavailable"
    )
    raw["ctc_timestamps"]["error"] = "alignment_failed"
    assert (
        alignment.playback_alignment(raw, "Hello there.", 1)["status"] == "unavailable"
    )


def test_alignment_order_may_differ_for_overlapping_speaker_turns(alignment):
    raw = response()
    raw["ctc_timestamps"]["words"].reverse()
    result = alignment.playback_alignment(raw, "there. Hello", 1)
    assert result["status"] == "ready"
    assert result["words"][0]["word"] == "Hello"


def test_request_opts_in_without_replacing_model_or_audio(alignment):
    request = {
        "payload": {
            "model": "pinned-model",
            "messages": [
                {
                    "content": [
                        {"type": "text", "text": "Verbatim."},
                        {"type": "audio_url", "audio_url": {"url": "captured"}},
                    ]
                }
            ],
        }
    }
    audio = copy.deepcopy(request["payload"]["messages"][0]["content"][1])
    alignment.request_timestamps(request)
    assert request["payload"]["messages"][0]["content"][1] == audio
    assert request["payload"]["model"] == "pinned-model"
    assert request["payload"]["mm_processor_kwargs"] == {"capture_ctc_timestamps": True}
