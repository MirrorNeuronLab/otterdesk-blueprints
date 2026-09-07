"""Validate architecture policy budgets from SDK-resolved configuration."""
from copy import deepcopy
from pathlib import Path


def bundled_path(relative):
    return Path(__file__).resolve().parents[1] / relative


def validate_config(value):
    config = deepcopy(value)
    if not isinstance(config.get("offline"), bool):
        raise ValueError("offline must be a boolean")
    config["llm"].setdefault("model", "default")
    for section, keys in {
        "source": ["clone_timeout_seconds"],
        "knowledge": ["max_cards", "max_prompt_bytes"],
        "llm": ["context_tokens", "output_tokens", "timeout_seconds", "max_calls"],
        "graph": ["timeout_seconds", "row_limit"],
        "investigation": ["max_hypotheses", "top_k", "max_queries", "max_rounds", "max_distinct_hypotheses", "timeout_seconds", "final_model_reserve"],
        "ingest": ["max_files", "max_file_bytes", "max_total_bytes", "chunk_chars", "git_commits"],
    }.items():
        for key in keys:
            v = config[section].get(key)
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                raise ValueError(f"{section}.{key} must be a positive integer")
    knowledge = config["knowledge"]
    if not isinstance(knowledge["enabled"], bool) or knowledge["max_cards"] > 4 or knowledge["max_prompt_bytes"] > 2400:
        raise ValueError("knowledge requires boolean enabled, at most 4 cards and 2400 prompt bytes")
    if knowledge["path"] is not None:
        if not isinstance(knowledge["path"], str) or not knowledge["path"].strip():
            raise ValueError("knowledge.path must be null or a JSON file path")
    if config["llm"]["context_tokens"] < config["llm"]["output_tokens"] + 2048:
        raise ValueError("Context budget must reserve at least 2048 input tokens")
    if config["llm"].get("structured_output", "json_schema") not in {"json_schema", "json_object"}:
        raise ValueError("llm.structured_output must be json_schema or json_object")
    if not isinstance(config["llm"].get("enable_thinking", False), bool):
        raise ValueError("llm.enable_thinking must be a boolean")
    if config["embedding"]["mode"] not in {"neural", "hash"}:
        raise ValueError("embedding.mode must be neural or hash")
    if config["investigation"]["max_hypotheses"] > 10 or config["graph"]["row_limit"] > 100:
        raise ValueError("At most 10 hypotheses and 100 result rows are supported")
    if config["investigation"]["max_rounds"] > 3 or config["investigation"]["max_hypotheses"] > 3:
        raise ValueError("Declared child workflow admits at most three rounds and hypotheses per round")
    if config["llm"]["max_calls"] <= config["investigation"]["final_model_reserve"]:
        raise ValueError("Model budget must exceed the final review reserve")
    return config


def offline_config(config):
    result = deepcopy(config)
    result["embedding"]["mode"] = "hash"
    return result
