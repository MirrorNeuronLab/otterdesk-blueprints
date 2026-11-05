"""Read-only retrospective questions with frozen time bounds and durable receipts."""

import asyncio
import hashlib
from datetime import datetime

import httpx

from .visual_history import search_interval
from .window_evidence import box_coordinates, chat_frame


class VideoQuestions:
    def __init__(self, history, client, model):
        self.history, self.store, self.client, self.model = history, history.store, client, model
        self.tasks = {}
        self.closing = False

    def submit(self, command_id, question, after, before):
        if not command_id.strip() or len(command_id) > 128 or not question.strip() or len(question.encode()) > 8000:
            raise ValueError("Enter a bounded question about saved footage.")
        key = "video:" + command_id
        request = {"question": question, "after": after, "before": before, "run": self.store.run_id, "source": self.store.source_id}
        if not self.store.command(key, request):
            lower, upper = search_interval(question, after, before)
            self.store.command(key, request, {"command_id": command_id, "state": "accepted", "owner": self.store.run_id,
                "source": self.store.source_id, "question": question, "after": lower, "before": upper})
        return self.status(command_id)

    def status(self, command_id):
        key = "video:" + command_id
        record = self.store.command(key)
        if not record or record["owner"] != self.store.run_id or record["source"] != self.store.source_id:
            raise ValueError("No saved-footage request has this ID for this run.")
        if record["state"] == "accepted" and key not in self.tasks:
            if self.closing or len(self.tasks) >= 4:
                record.update(state="failed", summary="Saved footage search is busy. Try again.")
                self.store.command(key, receipt=record)
            else:
                self.tasks[key] = asyncio.create_task(self._finish(key, record.copy()))
        return {k: v for k, v in record.items() if k not in {"owner", "source", "question"}}

    async def _finish(self, key, receipt):
        try:
            async with asyncio.timeout(75):
                result = await asyncio.to_thread(self.history.search, receipt["question"], receipt["after"], receipt["before"])
                report = await self._review(receipt["question"], result)
            receipt.update(state="completed", **report)
        except asyncio.CancelledError:
            receipt.update(state="cancelled", summary="The saved footage search stopped with this run.")
        except Exception:
            receipt.update(state="failed", summary="Couldn't search saved footage. Check history indexing and video analysis, then try again.")
        finally:
            self.store.command(key, receipt=receipt)
            self.tasks.pop(key, None)

    async def _review(self, question, result):
        citations, descriptions, matched = [], [], False
        image = None
        image_rank = -1
        review_error = False
        for account in result["observations"]:
            via_image = account["matched_via"] == "image"
            jpeg = self.store.frame(account["id"]) if via_image else None
            if via_image and (not jpeg or hashlib.sha256(jpeg).hexdigest() != account["snapshot"]["sha256"]):
                raise ValueError("The ranked camera image has changed.")
            try:
                verdict, summary, box = await self.client.review(self.model(), question, jpeg=jpeg, caption=account["content"])
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                review_error = True
                break
            matched |= verdict == "matched"
            t = account["snapshot"]["received_at"] if via_image else account["start_time"]
            display = datetime.fromisoformat(t).strftime("%b %d, %H:%M:%S UTC")
            descriptions.append((verdict, f"{display} ({'saved image' if via_image else 'window caption'}) — {summary}"))
            citations.append({"citation": account["source_refs"][0], "run_id": account["run_id"],
                              "start_time": account["start_time"], "end_time": account["end_time"],
                              "source": account["matched_via"], "verdict": verdict})
            # Show the best reviewed still even when the answer is uncertain or
            # negative. Its caption retains that verdict; retrieval is not proof.
            rank = {"matched": 2, "uncertain": 1, "not_matched": 0}.get(verdict, 1)
            if jpeg and rank > image_rank:
                if frame := chat_frame(account, jpeg, box_coordinates(box) if verdict == "matched" else None):
                    frame["caption"] += f" Review: {verdict.replace('_', ' ')}. {summary}"
                    image = {**frame, "citation": account["source_refs"][0]}
                    image_rank = rank
        if not result["total"]:
            lead = "There are no saved observations for this camera in that interval."
        elif not result["indexed"]:
            lead = "The saved observations in that interval are still waiting to be indexed."
        elif review_error and not descriptions:
            lead = "I found candidates in the index, but video analysis couldn't review them. Check camera analysis and try again."
        elif not descriptions:
            lead = result.get("limitation") or "The index returned no candidates in that interval."
        elif matched:
            lead = "I found a possible match in the saved observations."
        else:
            lead = "I couldn't confirm a match in the samples I reviewed."
        examples = [text for verdict, text in descriptions if verdict == "matched"] if matched else [text for _, text in descriptions[:2]]
        lines = [lead, *examples]
        if result.get("limitation") and result["limitation"] != lead:
            lines.append(result["limitation"])
        if review_error and descriptions:
            lines.append("Video analysis couldn't finish reviewing the remaining candidates.")
        lower, upper = (datetime.fromisoformat(result[k]).strftime("%b %d, %H:%M UTC") if result[k] else ""
                        for k in ("after", "before"))
        interval = " ".join(filter(None, ["from " + lower if lower else "", "through " + upper if upper else ""]))
        lines.append((f"Searched {interval}. " if interval else "") + f"{result['indexed']} of {result['total']} saved windows indexed. "
                     f"Reviewed {len(citations)} candidate{'s' if len(citations) != 1 else ''}.")
        return {"summary": "\n\n".join(lines), "citations": citations,
                **({"image": image} if image else {}),
                "indexed_count": result["indexed"], "window_count": result["total"]}

    async def close(self):
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
