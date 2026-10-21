"""Run the agent only after validated deterministic ingestion."""

from mn_sdk.blueprint_support import source_manifest
from .indexing import validate_indexes
from .app.agentic import run_investigation
from .app.review import build_review


def investigate(context, inputs):
    from .state import read_indexed, terminal, read_terminal, json_reference, terminal_result
    indexed = inputs["previous"]["result"]["evidence"]
    _, captured = read_indexed(context, indexed)
    if context.store.path("case/terminal.json").exists():
        reference = json_reference(context, "case/terminal.json", kind="block_checkpoint")
        prior = read_terminal(context, {"terminal": reference})
        if prior["indexed"] != indexed or prior["inputs"] != captured["inputs"] or "context" in prior:
            raise ValueError("Autonomous case terminal belongs to another investigation")
        return terminal_result(reference, prior)
    case = context.store.run_dir / "case"
    corpus, receipt = validate_indexes(
        case, context.config["investigation"]["access_scope"]
    )
    state, store = run_investigation(
        case,
        corpus,
        receipt,
        context,
        context.resources.get("llm"),
        goal=captured["inputs"]["goal"],
        declared=[d["name"] for d in source_manifest(__file__)["skill_dependencies"]],
    )
    summary = build_review(state, store, captured["inputs"]["goal"])
    return terminal(context, indexed, captured["inputs"], state, summary)


def verified(context, result):
    from .state import read_terminal
    read_terminal(context, result)
    return True
