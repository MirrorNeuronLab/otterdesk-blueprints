from __future__ import annotations

import json
from typing import Any, Callable

from .constants import INPUT_ADAPTERS, WEB_UI_ADAPTERS
from .observability import list_runs, load_run
from .user_config import interactive_first_run_setup, load_user_config
from .utils import deep_merge


def build_cli_parser(description: str = "Run a MirrorNeuron blueprint.") -> Any:
    import argparse

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("blueprint_id", nargs="?", help="Blueprint identifier to run.")
    parser.add_argument("--input-json", default=None, help="JSON object with input overrides.")
    parser.add_argument("--input-file", default=None, help="Load input overrides from a JSON file.")
    parser.add_argument("--input-adapter", default=None, choices=list(INPUT_ADAPTERS))
    parser.add_argument("--config", default=None, help="Path to a blueprint config JSON file.")
    parser.add_argument("--config-json", default=None, help="Inline config JSON object.")
    parser.add_argument("--user-config", default=None, help="Path to local MirrorNeuron user config.")
    parser.add_argument("--setup", action="store_true", help="Create or update the local MirrorNeuron user config.")
    parser.add_argument("--non-interactive-setup", action="store_true", help="Use default setup values without prompts.")
    parser.add_argument("--force-setup", action="store_true", help="Overwrite existing local user config during setup.")
    parser.add_argument("--run-id", default=None, help="Optional stable execution ID.")
    parser.add_argument("--runs-root", default=None, help="Override the global run store root.")
    parser.add_argument("--no-run-store", action="store_true", help="Disable writing ~/.mn/runs artifacts.")
    parser.add_argument("--list-runs", action="store_true", help="List recent run records.")
    parser.add_argument("--show-run", default=None, help="Load a run record by run_id.")
    parser.add_argument("--max-runs", type=int, default=20, help="Maximum runs to list.")
    parser.add_argument("--steps", type=int, default=None, help="Common simulation step override.")
    parser.add_argument("--seed", type=int, default=None, help="Common deterministic seed override.")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic fake LLM instead of live provider.")
    parser.add_argument("--web-ui", action="store_true", help="Enable shared blueprint web UI input/output support.")
    parser.add_argument("--no-web-ui", action="store_true", help="Disable shared blueprint web UI artifacts.")
    parser.add_argument("--web-ui-input-adapter", default=None, choices=list(WEB_UI_ADAPTERS), help="Override web UI input adapter.")
    parser.add_argument("--web-ui-output-adapter", default=None, choices=list(WEB_UI_ADAPTERS), help="Override web UI output adapter.")
    parser.add_argument("--web-ui-url", default=None, help="Register a customer-managed web UI URL for this run.")
    return parser


def run_blueprint_cli(
    run_func: Callable[..., dict[str, Any]],
    argv: list[str] | None = None,
    *,
    description: str = "Run a MirrorNeuron blueprint.",
    default_blueprint_id: str | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    parser = build_cli_parser(description)
    args = parser.parse_args(argv)
    output_fn = output_fn or print

    user_config = {}
    if args.setup:
        user_config = interactive_first_run_setup(
            args.user_config,
            force=args.force_setup,
            non_interactive=args.non_interactive_setup,
        )
        output_fn(json.dumps({"setup": user_config.get("setup"), "config_path": user_config.get("setup", {}).get("path")}, indent=2, sort_keys=True))
        if not args.blueprint_id and not default_blueprint_id and not args.list_runs and not args.show_run:
            return user_config
    else:
        user_config = load_user_config(args.user_config)

    runs_root = args.runs_root or ((user_config.get("outputs") or {}).get("run_root") if user_config else None)
    if args.list_runs:
        rows = list_runs(runs_root=runs_root, blueprint_id=args.blueprint_id or default_blueprint_id, limit=args.max_runs)
        output_fn(json.dumps(rows, indent=2, sort_keys=True))
        return rows
    if args.show_run:
        record = load_run(args.show_run, runs_root=runs_root)
        output_fn(json.dumps(record, indent=2, sort_keys=True))
        return record

    blueprint_id = args.blueprint_id or default_blueprint_id
    if not blueprint_id:
        parser.error("blueprint_id is required unless --setup, --list-runs, or --show-run is used")

    inputs: dict[str, Any] = {}
    if args.input_json:
        decoded = json.loads(args.input_json)
        if not isinstance(decoded, dict):
            parser.error("--input-json must decode to a JSON object")
        inputs.update(decoded)
    if args.steps is not None:
        inputs["steps"] = args.steps
    if args.seed is not None:
        inputs["seed"] = args.seed

    config_override = user_config_runtime_overrides(user_config)
    if args.mock_llm:
        config_override = deep_merge(config_override, {"llm": {"mode": "fake"}})
    web_ui_override: dict[str, Any] = {}
    if args.web_ui:
        web_ui_override["enabled"] = True
    if args.no_web_ui:
        web_ui_override["enabled"] = False
    if args.web_ui_input_adapter:
        web_ui_override.setdefault("input", {})["adapter"] = args.web_ui_input_adapter
    if args.web_ui_output_adapter:
        web_ui_override.setdefault("output", {})["adapter"] = args.web_ui_output_adapter
    if args.web_ui_url:
        web_ui_override.setdefault("output", {})["adapter"] = "custom"
        web_ui_override.setdefault("output", {})["custom_url"] = args.web_ui_url
    if web_ui_override:
        config_override = deep_merge(config_override, {"web_ui": web_ui_override})

    result = run_func(
        blueprint_id,
        inputs=inputs,
        config=config_override or None,
        config_path=args.config,
        config_json=args.config_json,
        run_id=args.run_id,
        runs_root=runs_root,
        input_adapter=args.input_adapter,
        input_file=args.input_file,
        write_run_store=False if args.no_run_store else None,
    )
    output_fn(json.dumps(result, indent=2, sort_keys=True))
    return result


def user_config_runtime_overrides(user_config: dict[str, Any]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for section in ("llm", "outputs", "logging", "web_ui"):
        value = user_config.get(section)
        if isinstance(value, dict):
            overrides[section] = value
    return overrides


_user_config_runtime_overrides = user_config_runtime_overrides
