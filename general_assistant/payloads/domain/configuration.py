"""Computer-use admission and bounded execution settings."""
from mn_computer_use_skill import require_mac
from mn_sdk.execution_mode import fake_llm_mode_enabled, fake_skills_mode_enabled


def settings(block):
    require_mac()
    if (fake_llm_mode_enabled(block.config, env=block.environment)
            or fake_skills_mode_enabled(block.config, env=block.environment)):
        raise ValueError("Live computer control is disabled when fake models or skills are selected")
    values = dict(block.config["computer_use"])
    for key, maximum in {"max_turns": 100, "max_questions": 12, "walltime_seconds": 3300,
                         "human_timeout_seconds": 600, "model_timeout_seconds": 120}.items():
        if type(values.get(key)) is not int or not 1 <= values[key] <= maximum:
            raise ValueError(f"computer_use.{key} must be in 1..{maximum}")
    if not block.config.get("text_memory", {}).get("enabled") or block.config.get("offline"):
        raise ValueError("Computer Use requires the enabled Membrane memory engine")
    return values


def read_value(block, value):
    return block.store.read(value) if value.get("type") == "artifact_ref" else value
