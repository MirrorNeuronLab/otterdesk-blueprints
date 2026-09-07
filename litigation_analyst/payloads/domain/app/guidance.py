"""Retrieve attributed methodology separately from confidential case evidence."""

import json
from pathlib import Path
from mn_sdk_rag.lexical import LexicalKnowledgeIndex


class InvestigationGuidance:
    def __init__(self):
        path = Path(__file__).resolve().parents[1] / "knowledge" / "guidance.json"
        self.index = LexicalKnowledgeIndex(json.loads(path.read_text(encoding="utf-8")))
        self.fingerprint = self.index.fingerprint

    def retrieve(self, phase, enquiry):
        result = self.index.retrieve(
            f"{phase} investigation evidence {enquiry}"[:8000], top_k=5
        )
        if not result["citations"]:
            raise ValueError(
                "required investigation guidance retrieval produced no citations"
            )
        return {
            **result,
            "role": "background guidance, never case evidence or permission",
            "applicability": "Jurisdiction and historical applicability require human review.",
        }
