"""Small local review library; bounded guidance is separate from project evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .config import bundled_path
from .model import SYSTEM
from .events import emit

DEFAULTS = {"enabled": True, "path": None, "max_cards": 2, "max_prompt_bytes": 1200}
GUIDANCE = ("\nUse architecture_guidance to choose verification checks, counter-checks and reversible actions. "
            "These general practices are not project facts. Never cite K IDs as repository evidence; "
            "support conclusions only with the supplied query/source IDs.")


def json_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


class KnowledgeBase:
    def __init__(self, config):
        self.settings = {**DEFAULTS, **config.get("knowledge", {})}
        self.cards = []
        self.audit = {"enabled": self.settings["enabled"], "version": None, "sha256": None,
                      "retrieval": "local family/keyword ranking; guidance is not repository evidence",
                      "selections": [], "cards": {}}
        if not self.settings["enabled"]:
            return
        path = Path(self.settings["path"]) if self.settings["path"] else bundled_path("knowledge/practices.json")
        raw = path.read_bytes()
        if len(raw) > 256_000:
            raise ValueError("Architecture knowledge file exceeds 256 KB MVP limit")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("version"), str) or not value["version"]:
            raise ValueError("Architecture knowledge requires a version")
        cards = value.get("cards")
        if not isinstance(cards, list) or not 1 <= len(cards) <= 50:
            raise ValueError("Architecture knowledge requires 1–50 cards")
        seen = set()
        for card in cards:
            if not isinstance(card, dict) or not re.fullmatch(r"K[0-9]{2,4}", card.get("id", "")) or card["id"] in seen:
                raise ValueError("Architecture knowledge card IDs must be unique K numbers")
            seen.add(card["id"])
            for field in ("title", "principle", "verify", "exception", "origin"):
                if not isinstance(card.get(field), str) or not card[field].strip() or len(card[field]) > 1000:
                    raise ValueError(f"Invalid architecture knowledge field: {field}")
            for field in ("families", "keywords"):
                if not isinstance(card.get(field), list) or not card[field] or any(not isinstance(s, str) or not s.strip() for s in card[field]):
                    raise ValueError(f"Invalid architecture knowledge field: {field}")
            if not isinstance(card.get("sources"), list) or any(
                not isinstance(s, dict) or not isinstance(s.get("title"), str) or
                not isinstance(s.get("url"), str) or not s["url"].startswith("https://") for s in card["sources"]
            ):
                raise ValueError("Architecture knowledge sources require titles and HTTPS links")
        self.cards = cards
        self.audit.update(version=value["version"], sha256=hashlib.sha256(raw).hexdigest())

    def select(self, goal, family=None, byte_limit=None):
        words = set(re.findall(r"\w+", goal.casefold()))
        scored = [(100 * (family in card["families"]) + len(words.intersection(card["keywords"])), card)
                  for card in self.cards]
        # Family matches take priority; no unrelated cards are added to fill the quota.
        ranked = [card for score, card in sorted(scored, key=lambda pair: (-pair[0], pair[1]["id"])) if score > 0]
        if not ranked and self.cards:
            ranked = [next((c for c in self.cards if c["id"] == "K01"), self.cards[0])]
        limit = min(self.settings["max_prompt_bytes"], byte_limit if byte_limit is not None else self.settings["max_prompt_bytes"])
        selected = []
        for card in ranked:
            compact = {k: card[k] for k in ("id", "title", "principle", "verify", "exception")}
            if json_bytes([*selected, compact]) <= limit:
                selected.append(compact)
            if len(selected) >= self.settings["max_cards"]:
                break
        return selected

    def record(self, stage, cards, model_requested=False):
        ids = [card["id"] for card in cards]
        self.audit["selections"].append({"stage": stage, "card_ids": ids, "prompt_bytes": json_bytes(cards),
                                         "model_requested": model_requested})
        for card in self.cards:
            if card["id"] in ids:
                self.audit["cards"][card["id"]] = card
        emit("knowledge.selected", stage=stage, card_ids=ids, prompt_bytes=json_bytes(cards), model_requested=model_requested)
        return ids


def with_guidance(knowledge, config, instruction, data, goal, family=None, reserve=0):
    """Reserve evidence/output/repair room before selecting a bounded knowledge packet."""
    base = dict(data)
    base["architecture_guidance"] = []
    overhead = len((SYSTEM + "\n" + instruction).encode()) + 256 + json_bytes(base)
    room = config["llm"]["context_tokens"] - config["llm"]["output_tokens"] - overhead - reserve - 200
    base["architecture_guidance"] = knowledge.select(goal, family, max(0, room))
    return base


def evidence_room(config, instruction, data):
    overhead = len((SYSTEM + "\n" + instruction).encode()) + 256 + json_bytes(data)
    return config["llm"]["context_tokens"] - config["llm"]["output_tokens"] - overhead - 200
