from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from .config import config_summary, load_config, validate_config
from .constants import BLUEPRINT_CATEGORIES
from .observability import list_runs, load_run, read_run_events
from .scaffold import scaffold_blueprint
from .user_config import interactive_first_run_setup, load_user_config, save_user_config
from .validation import validate_blueprint_directory


def build_management_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MirrorNeuron blueprint management tools.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    setup = subcommands.add_parser("setup", help="Create or update local user config.")
    setup.add_argument("--user-config", default=None)
    setup.add_argument("--force", action="store_true")
    setup.add_argument("--non-interactive", action="store_true")

    create = subcommands.add_parser("create", help="Scaffold a new blueprint.")
    create.add_argument("blueprint_id")
    create.add_argument("--root", default=".")
    create.add_argument("--category", choices=list(BLUEPRINT_CATEGORIES), default=None)
    create.add_argument("--description", default=None)
    create.add_argument("--force", action="store_true")

    config = subcommands.add_parser("config", help="Inspect or validate blueprint config.")
    config.add_argument("blueprint_id")
    config.add_argument("--root", default=".")
    config.add_argument("--config", default=None)
    config.add_argument("--config-json", default=None)
    config.add_argument("--run-id", default=None)
    config.add_argument("--runs-root", default=None)
    config.add_argument("--input-file", default=None)
    config.add_argument("--input-adapter", default=None)
    config.add_argument("--print", dest="print_config", action="store_true")
    config.add_argument("--validate", action="store_true")

    validate = subcommands.add_parser("validate", help="Validate a blueprint directory.")
    validate.add_argument("path")

    runs = subcommands.add_parser("runs", help="List recent runs.")
    runs.add_argument("--runs-root", default=None)
    runs.add_argument("--blueprint-id", default=None)
    runs.add_argument("--max-runs", type=int, default=20)

    show = subcommands.add_parser("show-run", help="Show a complete run record.")
    show.add_argument("run_id")
    show.add_argument("--runs-root", default=None)

    events = subcommands.add_parser("events", help="Show run events.")
    events.add_argument("run_id")
    events.add_argument("--runs-root", default=None)

    user_config = subcommands.add_parser("user-config", help="Inspect or update local user config.")
    user_config.add_argument("--path", default=None)
    user_config.add_argument("--set-json", default=None, help="Merge a JSON object into the user config.")

    return parser


def main(argv: list[str] | None = None, *, output_fn: Callable[[str], None] | None = None) -> object:
    parser = build_management_parser()
    args = parser.parse_args(argv)
    output_fn = output_fn or print

    if args.command == "setup":
        result = interactive_first_run_setup(args.user_config, force=args.force, non_interactive=args.non_interactive)
    elif args.command == "create":
        result = scaffold_blueprint(
            args.blueprint_id,
            target_root=args.root,
            category=args.category,
            description=args.description,
            force=args.force,
        )
    elif args.command == "config":
        root = Path(args.root)
        default_config_path = root / args.blueprint_id / "config" / "default.json"
        config = load_config(
            args.blueprint_id,
            default_config_path=default_config_path if default_config_path.exists() else None,
            config_path=args.config,
            config_json=args.config_json,
            run_id=args.run_id,
            runs_root=args.runs_root,
            input_file=args.input_file,
            input_adapter=args.input_adapter,
        )
        result = {
            "summary": config_summary(config),
            "issues": validate_config(config, blueprint_id=args.blueprint_id),
        }
        if args.print_config:
            result["config"] = config
    elif args.command == "validate":
        result = validate_blueprint_directory(args.path)
    elif args.command == "runs":
        result = list_runs(runs_root=args.runs_root, blueprint_id=args.blueprint_id, limit=args.max_runs)
    elif args.command == "show-run":
        result = load_run(args.run_id, runs_root=args.runs_root)
    elif args.command == "events":
        result = read_run_events(args.run_id, runs_root=args.runs_root)
    elif args.command == "user-config":
        if args.set_json:
            updates = json.loads(args.set_json)
            if not isinstance(updates, dict):
                parser.error("--set-json must decode to a JSON object")
            current = load_user_config(args.path)
            current.update(updates)
            result = save_user_config(current, args.path)
        else:
            result = load_user_config(args.path)
    else:
        parser.error(f"unknown command {args.command}")

    output_fn(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    main()
