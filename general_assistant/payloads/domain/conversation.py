"""Expose task entry, observed Harness2 progress and clarifications in Chat."""
import time
import threading
import json

from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk import human_interactions


class Conversation:
    def __init__(self, block):
        self.block = block
        self.questions_lock = threading.Lock()
        self.answers = {}

    def context(self):
        with self.questions_lock:
            return ("\nHuman replies for this task (apply these constraints; do not ask them again):\n" +
                    json.dumps(self.answers, ensure_ascii=False)) if self.answers else ""

    def notice(self, identity, message):
        self.block.check()
        human_interactions.publish_human_interaction_event(
            self.block.run_id, "human_notice", {
                "request_id": fingerprint([self.block.invocation_id, identity]),
                "title": "General assistant", "message": message, "blocking": False,
            })

    def ask(self, identity, question, *, timeout=600):
        # Harness2 can probe concurrently. Serialize admission of the same reply
        # checkpoint rather than dispatching two recursive block effects.
        with self.questions_lock:
            reply = self._ask(identity, question, timeout=timeout)
            self.answers[question] = reply
            return reply

    def _ask(self, identity, question, *, timeout):
        self.block.check()
        if not isinstance(question, str) or not question.strip() or len(question.encode()) > 8000:
            raise ValueError("A conversation question must contain 1..8000 UTF-8 bytes")
        request_id = fingerprint([self.block.invocation_id, identity, question])
        def receive():
            plan = self.block.freeze_checkpoint(self.block.root + "/conversation/" + request_id + ".json",
                lambda: {"expires_at": int(time.time() * 1000) + int(timeout * 1000)})
            expires_at = self.block.store.read(plan)["data"]["expires_at"]
            remaining = min(timeout, (expires_at - time.time() * 1000) / 1000)
            if remaining <= 0:
                raise RuntimeError("The conversation input expired. Start a new run to continue.")
            human_interactions.publish_human_interaction_event(
                self.block.run_id, "human_input_requested", {
                    "request_id": request_id, "interaction_kind": "missing_information",
                    "prompt": question, "blocking": True, "options": [], "expires_at": expires_at,
                })
            event = human_interactions.await_human_decision(self.block.run_id, request_id, timeout=remaining)
            self.block.check()
            payload = event.get("payload", {})
            if (event.get("type") != "human_input_received" or payload.get("request_id") != request_id
                    or payload.get("decision") in {"reject", "cancel"}):
                raise RuntimeError("The task needs a reply in Chat before it can continue")
            answer = payload.get("notes")
            if not isinstance(answer, str) or not answer.strip() or len(answer.encode()) > 8000:
                raise ValueError("The conversation reply must contain 1..8000 UTF-8 bytes")
            return {"reply": answer.strip()}
        reference = self.block.freeze_checkpoint(
            self.block.root + "/conversation/" + request_id + "-reply.json", receive)
        return self.block.store.read(reference)["data"]["reply"]
