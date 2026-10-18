"""Bounded attorney review profiles, independent of runtime scheduling."""
from copy import deepcopy


def limits(config):
    profile = config.get("review", {}).get("profile", "standard")
    if profile not in {"first_pass", "standard"}:
        raise ValueError("review.profile must be first_pass or standard")
    settings = config["dynamic_investigation"]
    first = profile == "first_pass"
    return {"profile": profile,
            "max_rounds": min(settings["max_rounds"], 1 if first else 3),
            "hypotheses_per_round": settings["hypotheses_per_round"],
            "seconds": min(config["investigation"]["max_investigation_seconds"], 600 if first else 99999),
            "max_decisions": min(config["investigation"]["max_model_decisions"], 6 if first else 16),
            "relationship_mode": "structural" if first else config["source_relationships"]["mode"],
            "relationship_call_ceiling": 0 if first else config["source_relationships"]["max_calls"],
            "definition": "Decision ceilings exclude provider transport/repair attempts; elapsed limits are checked at planning boundaries. Ranked retrieval is not exhaustive."}


def decision_config(config):
    result = deepcopy(config)
    if "review" in config:
        ceiling = limits(config)["max_decisions"]
        result["context_memory"]["policy"].update(max_calls=min(result["context_memory"]["policy"]["max_calls"], ceiling), final_call_reserve=0)
    return result
