"""Small plain-text RAG helper for the pizza-ordering voice co-worker."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_'-]*", re.IGNORECASE)


@dataclass(frozen=True)
class KnowledgeChunk:
    """A retrievable knowledge chunk."""

    chunk_id: str
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalResult:
    """A scored retrieved knowledge chunk."""

    chunk_id: str
    text: str
    score: float


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text or "")]


def chunk_text(text: str, *, max_tokens: int = 120, overlap: int = 24) -> list[KnowledgeChunk]:
    """Split plain text into overlapping lexical chunks."""

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text or "") if part.strip()]
    if not paragraphs:
        return []

    chunks: list[KnowledgeChunk] = []
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        chunk_text_value = "\n\n".join(pending).strip()
        tokens = tuple(tokenize(chunk_text_value))
        if tokens:
            chunks.append(KnowledgeChunk(f"k{len(chunks) + 1:04d}", chunk_text_value, tokens))
        pending = []

    for paragraph in paragraphs:
        paragraph_tokens = tokenize(paragraph)
        if len(paragraph_tokens) > max_tokens:
            flush()
            step = max(max_tokens - overlap, 1)
            for start in range(0, len(paragraph_tokens), step):
                token_slice = paragraph_tokens[start : start + max_tokens]
                if not token_slice:
                    continue
                chunks.append(
                    KnowledgeChunk(
                        f"k{len(chunks) + 1:04d}",
                        " ".join(token_slice),
                        tuple(token_slice),
                    )
                )
                if start + max_tokens >= len(paragraph_tokens):
                    break
            continue

        pending_tokens = tokenize("\n\n".join(pending + [paragraph]))
        if pending and len(pending_tokens) > max_tokens:
            flush()
        pending.append(paragraph)

    flush()
    return chunks


def retrieve(
    query: str,
    chunks: Iterable[KnowledgeChunk],
    *,
    top_k: int = 4,
    min_score: float = 0.01,
) -> list[RetrievalResult]:
    """Return top matching chunks using a lightweight TF-style lexical score."""

    query_tokens = tokenize(query)
    if not query_tokens or top_k <= 0:
        return []

    query_counts: dict[str, int] = {}
    for token in query_tokens:
        query_counts[token] = query_counts.get(token, 0) + 1

    results: list[RetrievalResult] = []
    for chunk in chunks:
        if not chunk.tokens:
            continue
        chunk_counts: dict[str, int] = {}
        for token in chunk.tokens:
            chunk_counts[token] = chunk_counts.get(token, 0) + 1

        overlap_terms = set(query_counts) & set(chunk_counts)
        if not overlap_terms:
            continue

        raw = 0.0
        for token in overlap_terms:
            raw += math.sqrt(query_counts[token]) * math.sqrt(chunk_counts[token])
        coverage = len(overlap_terms) / max(len(set(query_counts)), 1)
        length_penalty = math.sqrt(len(chunk.tokens))
        score = (raw * (0.35 + coverage)) / max(length_penalty, 1.0)
        if score >= min_score:
            results.append(RetrievalResult(chunk.chunk_id, chunk.text, round(score, 6)))

    results.sort(key=lambda item: (-item.score, item.chunk_id))
    return results[:top_k]


def build_rag_context(query: str, knowledge_text: str, *, top_k: int = 4) -> tuple[str, list[RetrievalResult]]:
    """Build an LLM-ready snippet block from plain-text knowledge."""

    chunks = chunk_text(knowledge_text)
    results = retrieve(query, chunks, top_k=top_k)
    if not results:
        return "No matching customer knowledge snippets were found for this turn.", []
    lines = []
    for index, result in enumerate(results, start=1):
        lines.append(f"[{index}] {result.text}")
    return "\n\n".join(lines), results
