"""Runtime-boundary adapters for Financial Advisor."""

from .legacy import append_event, runtime_context_for_step

__all__ = ["append_event", "runtime_context_for_step"]

