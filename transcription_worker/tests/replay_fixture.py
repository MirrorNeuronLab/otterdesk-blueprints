"""Synthetic speech-shaped audio and timing evidence; never a model quality claim."""

import io
import math
from pathlib import Path
import struct
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payloads"))
from domain.reporting import render


def write_fixture(root):
    root = Path(root)
    (root / "audio").mkdir(parents=True, exist_ok=True)
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(
            b"".join(
                struct.pack("<h", int(500 * math.sin(2 * math.pi * 220 * i / 16000)))
                for i in range(16000 * 8)
            )
        )
    (root / "audio/section.wav").write_bytes(audio.getvalue())
    chunks = []
    for section in range(2):
        words = [
            {
                "word": word,
                "start": index * 0.08,
                "end": index * 0.08 + 0.07,
                "speaker": str(index // 5 % 3),
            }
            for index, word in enumerate(
                (
                    "We reviewed the recording together and agreed to follow up tomorrow. ".split()
                    * 8
                )[:90]
            )
        ]
        # Two speakers overlap for the first word; the rest follows actual time.
        words.insert(1, {"word": "Yes.", "start": 0.02, "end": 0.07, "speaker": "1"})
        if section:
            words = [{**word, "speaker": "0"} for word in words]
        chunks.append(
            {
                "index": section,
                "start_seconds": section * 8,
                "end_seconds": (section + 1) * 8,
                "audio": "audio/section.wav",
                "text": "Synthetic transcript fixture",
                "alignment": {
                    "status": "ready",
                    "words": words,
                    "speakers": ["0", "1", "2"] if section == 0 else ["0"],
                    "segments": [
                        {"start": 0, "end": 0.07, "speaker": "1"},
                        {"start": 0, "end": 1.2, "speaker": "0"},
                        {"start": 1.2, "end": 2.4, "speaker": "1"},
                        {"start": 2.4, "end": 3.6, "speaker": "2"},
                    ]
                    if section == 0
                    else [{"start": 0, "end": 7.2, "speaker": "0"}],
                },
            }
        )
    record = {
        "source": "Project discussion.wav",
        "source_sha256": "a" * 64,
        "duration_seconds": 16,
        "chunks": chunks,
    }
    recordings = [
        {"source": record["source"], "page": "index.html"},
        {"source": "Silent recording.wav", "page": "empty.html"},
    ]
    (root / "index.html").write_bytes(render(record, recordings, "synthetic-replay"))
    many = {
        **record,
        "source": "Eight speakers.wav",
        "chunks": [
            {
                **chunks[0],
                "alignment": {
                    **chunks[0]["alignment"],
                    "speakers": list(map(str, range(8))),
                    "segments": [
                        {"start": 0, "end": 8, "speaker": str(i)} for i in range(8)
                    ],
                },
            }
        ],
    }
    (root / "many.html").write_bytes(
        render(
            many, [{"source": many["source"], "page": "many.html"}], "synthetic-many"
        )
    )
    record = {
        **record,
        "source": recordings[1]["source"],
        "source_sha256": "b" * 64,
        "duration_seconds": 8,
        "chunks": [
            {
                **chunks[0],
                "text": "",
                "alignment": {
                    "status": "ready",
                    "words": [],
                    "speakers": [],
                    "segments": [],
                },
            }
        ],
    }
    (root / "empty.html").write_bytes(render(record, recordings, "synthetic-replay"))


if __name__ == "__main__":
    write_fixture(sys.argv[1])
