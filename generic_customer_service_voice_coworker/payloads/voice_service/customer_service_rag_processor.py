"""Pipecat frame processor that injects retrieved knowledge into each user turn."""

from __future__ import annotations

import os

from loguru import logger

from knowledge_store import read_knowledge
from rag import build_rag_context
from conversation_events import append_conversation, emit_event

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class CustomerServiceRAGInjector(FrameProcessor):
    """Replace final user transcripts with knowledge-augmented LLM prompts."""

    def __init__(self, *, top_k: int | None = None):
        super().__init__()
        self.top_k = top_k or int(os.getenv("CUSTOMER_SERVICE_RAG_TOP_K", "4"))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            original_text = frame.text.strip()
            knowledge_text = read_knowledge()
            context_text, results = build_rag_context(original_text, knowledge_text, top_k=self.top_k)
            append_conversation(
                "user",
                original_text,
                rag_chunk_ids=[result.chunk_id for result in results],
                rag_scores=[result.score for result in results],
            )
            emit_event(
                "customer_service_rag_context_selected",
                {
                    "query": original_text,
                    "chunk_ids": [result.chunk_id for result in results],
                    "scores": [result.score for result in results],
                },
            )
            logger.info(f"Selected {len(results)} knowledge chunks for customer turn")
            augmented = (
                "Customer said:\n"
                f"{original_text}\n\n"
                "Relevant editable customer knowledge for this turn:\n"
                f"{context_text}\n\n"
                "Answer the customer using only the relevant knowledge above and the standing system instructions. "
                "If the knowledge does not answer the question, ask one clarifying question or recommend escalation."
            )
            frame = TranscriptionFrame(
                augmented,
                frame.user_id,
                frame.timestamp,
                frame.language,
                result={
                    "original_text": original_text,
                    "rag_chunk_ids": [result.chunk_id for result in results],
                    "rag_scores": [result.score for result in results],
                },
            )

        await self.push_frame(frame, direction)

