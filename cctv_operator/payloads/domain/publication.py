"""Durable NVIDIA window accounts and restrained completed Chat activity."""

from pathlib import Path

from mn_sdk_common.files import atomic_write_json, atomic_write_text


class Publisher:
    def __init__(self, run_dir, store, exchange):
        self.run_dir, self.store, self.exchange = Path(run_dir), store, exchange

    def caption(self, caption):
        reference = caption["source_refs"][0]
        atomic_write_json(self.run_dir / reference, caption)
        markdown = (
            f"# {caption['camera']} — video observation\n\n"
            f"Capture interval: {caption['start_time']} to {caption['end_time']}\n\n"
            f"Analysis received: {caption['received_at']}\n\n"
            f"Monitoring goal: {caption['instruction']}\n\n"
            f"{caption['content']}\n\n"
            f"Source: {reference}\n\n"
            "This is a model description of a sampled video window. It can miss or misdescribe activity. "
            "It does not establish identity, unique-person counts, compliance or safety. "
            "The separate preview is current video, not the exact analyzed evidence.\n"
        )
        atomic_write_text(self.run_dir / "context_sources/outputs" / (Path(reference).stem + ".md"), markdown, create_parents=True)
        self.report()
        # Routine windows stay in the workspace. Chat receives the first completed
        # account for each applied goal, never a fabricated goal-match verdict.
        marker = f"activity:{self.store.run_id}:{caption['instruction_revision']}"
        if not self.store.state(marker):
            activity = {"schema_version": "mn.mcp.job_activity.v1", "event_id": caption["id"],
                        "title": "Video observation", "message": caption["content"],
                        "occurred_at": caption["received_at"], "source": "cctv_operator",
                        "requires_review": False,
                        "details": [f"Captured {caption['start_time']} to {caption['end_time']}",
                                    "Sampled NVIDIA video description; human review required for decisions."]}
            self.exchange.publish_result(caption["id"], activity, stage="live_activity",
                                         summary=caption["content"][:2000], publication_state="final",
                                         idempotency_key="caption:" + caption["id"])
            self.store.set_state(marker, caption["id"])

    def status(self, state):
        atomic_write_json(self.run_dir / "monitoring_state.json", state)
        self.report(state)

    def report(self, state=None):
        history = self.store.history(current_run=True)
        observations = history["observations"]
        report = {"schema_version": "otterdesk.cctv.report.v6", "run_id": self.store.run_id,
                  "source_id": self.store.source_id, "observations": observations,
                  "total_count": history["total_count"], "omitted_count": history["omitted_count"]}
        if state:
            report["session"] = state
        atomic_write_json(self.run_dir / "cctv_report.json", report)
        entries = [f"## {item['start_time']} to {item['end_time']}\n\n{item['content']}\n\nSource: {item['source_refs'][0]}"
                   for item in observations]
        atomic_write_text(self.run_dir / "cctv_report.md", "# CCTV observations\n\n"
                    + "Sampled model descriptions require human review. Missing captions do not establish a clear scene.\n\n"
                    + ("\n\n".join(entries) if entries else "No completed video observations yet.")
                    + f"\n\nEarlier observations omitted from this report: {history['omitted_count']}.\n")
        summary = observations[-1]["content"] if observations else "No completed video observations yet."
        atomic_write_json(self.run_dir / "final_artifact.json", {
            "type": "cctv_observations", "executive_summary": summary,
            "recommended_action": "Review the recorded video interval before acting.",
            "confidence": "Uncalibrated model description", "evidence": observations[-1:],
            "next_steps": ["Review the source video and any uncertainty."],
            "source_refs": ["cctv_report.json", "cctv_report.md"],
        })
