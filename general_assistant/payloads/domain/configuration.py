"""Validate the general assistant's task and execution allowances."""
from pathlib import Path
from contextlib import contextmanager
import os


def settings(block):
    values = dict(block.config["harness"])
    bounds = {
        "recursion_steps": (1, 3), "session_timeout_seconds": (1, 1200),
        "walltime_seconds": (1, 7200), "max_sessions": (1, 96),
        "max_input_files": (1, 512), "max_input_bytes": (1, 33554432),
        "max_output_files": (1, 512), "max_output_bytes": (1, 33554432),
        "max_memory_files": (1, 1024), "max_memory_bytes": (1, 8388608),
        "gateway_port": (1, 65535),
        "core_port": (1, 65535),
    }
    for key, (minimum, maximum) in bounds.items():
        if type(values.get(key)) is not int or not minimum <= values[key] <= maximum:
            raise ValueError(f"harness.{key} must be in {minimum}..{maximum}")
    if values.get("mode") not in {"sequential", "parallel"}:
        raise ValueError("harness.mode must be sequential or parallel")
    if values["core_port"] in {values["gateway_port"], 443}:
        raise ValueError("The Core conversation port must be separate from model and public HTTPS ports")
    if block.config.get("llm", {}).get("model", "default") != "default":
        raise ValueError("General Assistant consumes the runtime default model")
    return values


def read_value(block, value):
    return block.store.read(value) if value.get("type") == "artifact_ref" else value


def require_openshell():
    if b"openshell-sandbox" not in Path("/proc/1/cmdline").read_bytes():
        raise RuntimeError("Harness2 execution requires OpenShell")


@contextmanager
def core_connection(limits):
    """Bind the sandbox controller's route only for its encapsulated invocation."""
    previous = os.environ.get("MN_GRPC_TARGET")
    os.environ["MN_GRPC_TARGET"] = f"{limits['gateway_host']}:{limits['core_port']}"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MN_GRPC_TARGET", None)
        else:
            os.environ["MN_GRPC_TARGET"] = previous
