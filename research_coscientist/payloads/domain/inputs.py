"""Research-input normalization and local evidence intake."""

from .workflow import (
    expand_runtime_path,
    load_input_documents,
    normalize_inputs,
    resolve_input_folder,
)
from .operations import frame_goal

__all__ = [
    "expand_runtime_path",
    "load_input_documents",
    "normalize_inputs",
    "resolve_input_folder",
    "frame_goal",
]
