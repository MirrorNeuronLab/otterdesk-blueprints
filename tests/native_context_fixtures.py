"""Synthetic inputs for current consumers, independent of historical run folders."""

import base64
import json

# An original 8x8 solid-red JPEG, authored locally. Keeping its bytes avoids an
# imaging-library dependency in this native indexing/provenance test.
CAMERA_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAIAAgDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9"
    "AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6"
    "Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ip"
    "qrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEB"
    "AQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh"
    "cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpj"
    "ZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK"
    "0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z"
)


def vc_runtime_state(run_dir, roles):
    """Exercise qualification and role selection without claiming browser results."""
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence = {
        "source_records": [
            {
                "source_id": "synthetic-founder-note",
                "source_type": "founder_supplied",
                "source_quality_label": "unverified",
                "retrieved_at": "2026-11-01T12:00:00Z",
            }
        ],
        "evidence_items": [
            {
                "evidence_id": "synthetic-evidence",
                "source_id": "synthetic-founder-note",
            }
        ],
        "claim_records": [
            {
                "claim_id": "synthetic-" + family,
                "canonical_claim": "Synthetic unverified " + family + " claim",
                "claim_type": family + ".reported",
                "verification_status": "unverified",
                "required_next_evidence": ["Independent confirmation is missing."],
                "evidence_ids": ["synthetic-evidence"],
            }
            for family in ("team", "product", "finance", "traction")
        ],
    }
    events = [
        {
            "type": "observability_operation_failed",
            "timestamp": "2026-11-01T12:01:00Z",
            "payload": {
                "phase": "public_tool_call",
                "agent_id": role,
                "operation_id": "synthetic-tool-" + role,
                "operation": "synthetic_lookup",
                "status": "failed",
                "tool_status": "unavailable",
                "error": "Synthetic tool unavailable; no external confirmation.",
                "source_count": 0,
            },
        }
        for role in roles
    ]
    (run_dir / "llm_rag_trace.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8"
    )
    return {"evidence": {"Synthetic Company": evidence}, "cached": {"analyses": {}}}


class CameraEmbeddings:
    """Fixed vectors test native indexing/provenance, never semantic quality."""

    metadata = {"model": "synthetic-camera", "tokenizer": "synthetic-camera-v1"}
    vector = [1.0] + [0.0] * 767

    def embed(self, chunks):
        return {
            "vectors": [
                {
                    **chunk,
                    "end_byte": chunk["start_byte"] + len(chunk["text"].encode()),
                    "values": self.vector,
                }
                for chunk in chunks
            ]
        }

    def embed_media(self, media):
        assert media.data.startswith(b"\xff\xd8")
        return self.embed_query("")

    def embed_query(self, question):
        return {**self.metadata, "vector": self.vector}
