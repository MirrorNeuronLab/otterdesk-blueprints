from __future__ import annotations

from pathlib import Path


STANDARD_VERSION = "1.0"
DEFAULT_MN_HOME = Path("~/.mn")
DEFAULT_RUNS_ROOT = DEFAULT_MN_HOME / "runs"
DEFAULT_LOGS_ROOT = DEFAULT_MN_HOME / "logs"
DEFAULT_USER_CONFIG_PATH = DEFAULT_MN_HOME / "config.json"
DEFAULT_BLUEPRINT_LOG_PATH = DEFAULT_LOGS_ROOT / "blueprint-support.log"
LEGACY_MN_HOME = Path("~/.mirror_neuron")
LEGACY_RUNS_ROOT = LEGACY_MN_HOME / "runs"
LEGACY_USER_CONFIG_PATH = LEGACY_MN_HOME / "config.json"
BLUEPRINT_CATEGORIES = ("general", "business", "finance", "science")
INPUT_ADAPTERS = ("mock", "json", "file", "env_json")
OUTPUT_ADAPTERS = ("local_run_store",)
WEB_UI_ADAPTERS = ("none", "static_html", "gradio", "custom")
RUN_ARTIFACTS = ("run.json", "config.json", "inputs.json", "events.jsonl", "result.json", "final_artifact.json")
OPTIONAL_RUN_ARTIFACTS = ("job.json", "web_ui.json", "web/index.html")
CONFIG_SECTIONS = ("metadata", "identity", "inputs", "simulation", "llm", "outputs", "logging", "real_adapters", "web_ui")
EXECUTION_MODEL = (
    "load_metadata",
    "resolve_config",
    "load_inputs",
    "start_run_store",
    "observe_simulation_state",
    "call_llm_agent",
    "apply_decision_to_simulation",
    "emit_events",
    "write_final_artifact",
)
