"""Validate the model's measured timing evidence for the transcript replay."""

import math
import re
from collections import Counter

SPEAKER_TAG = re.compile(r"<spk:([0-7])>")


def request_timestamps(request):
    """Select this co-worker's speaker-attributed transcription policy."""
    payload = request["payload"]
    payload["messages"][0]["content"][0]["text"] += (
        " Put speaker tags <spk:0> through <spk:7> on the transcription."
    )
    payload["mm_processor_kwargs"] = {"capture_ctc_timestamps": True}
    payload["skip_special_tokens"] = False
    payload["stream"] = False
    payload["n"] = 1


def _interval(value, duration):
    start, end = value.get("start"), value.get("end")
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end)):
        raise ValueError("Invalid timestamp")
    # NeMo rounds frame times to milliseconds, including the final frame.
    if not 0 <= start <= end <= duration + 0.02:
        raise ValueError("Timestamp is outside the captured audio")
    return {"start": min(start, duration), "end": min(end, duration)}


def playback_alignment(response, text, duration):
    """Never estimate word times or infer identities across independent chunks.

    Transcripts remain authoritative if optional timing evidence is unavailable.
    A missing/failed/malformed alignment prevents publication of a replay, instead
    of showing guessed highlights or an invented number of people.
    """
    value = response.get("ctc_timestamps")
    if (
        not isinstance(value, dict)
        or "error" not in value
        or value["error"] is not None
    ):
        return {"status": "unavailable"}
    try:
        words, segments = value["words"], value["diarization"]
        mapping = value["speaker_tag_to_diarization_speaker"]
        if not isinstance(words, list) or len(words) > 20000:
            raise ValueError("Invalid words")
        if not isinstance(segments, list) or len(segments) > 60000:
            raise ValueError("Invalid speaker activity")
        if not isinstance(mapping, dict) or len(mapping) > 8:
            raise ValueError("Invalid speaker mapping")
        # NeMo uses numeric strings for speaker IDs in timestamp data.
        if any(
            not re.fullmatch(r"[0-7]", tag)
            or (
                speaker is not None
                and (type(speaker) is not int or not 0 <= speaker <= 7)
            )
            for tag, speaker in mapping.items()
        ):
            raise ValueError("Invalid speaker mapping")
        result_words, result_segments, speakers = [], [], set()
        for segment in segments:
            speaker = segment["speaker"]
            if type(speaker) is not int or not 0 <= speaker <= 7:
                raise ValueError("Invalid speaker")
            result_segments.append(
                {**_interval(segment, duration), "speaker": str(speaker)}
            )
            speakers.add(str(speaker))
        for word in words:
            label, tag = word["word"], word.get("speaker")
            if not isinstance(label, str) or not label.strip() or len(label) > 2048:
                raise ValueError("Invalid word")
            speaker = str(mapping[tag]) if mapping.get(tag) is not None else None
            result_words.append(
                {**_interval(word, duration), "word": label, "speaker": speaker}
            )
            if speaker is not None:
                speakers.add(speaker)
        if bool(SPEAKER_TAG.sub("", text).strip()) != bool(result_words):
            raise ValueError("Incomplete word alignment")
        # Keep all original text. Partial alignments must never silently drop words.
        # Overlapping turns are returned in time order, while generated text can
        # group turns by speaker. Preserve token multiplicity without pretending
        # that serialization order is the audio order.
        def tokens(value):
            return Counter(re.findall(r"\w+|[^\w\s]", SPEAKER_TAG.sub("", value)))

        if tokens(text) != tokens(" ".join(word["word"] for word in result_words)):
            raise ValueError("Alignment does not cover the transcript")
        return {
            "status": "ready",
            "words": sorted(result_words, key=lambda w: (w["start"], w["end"])),
            "segments": sorted(result_segments, key=lambda s: s["start"]),
            "speakers": sorted(speakers, key=int),
        }
    except (KeyError, TypeError, ValueError):
        return {"status": "unavailable"}
