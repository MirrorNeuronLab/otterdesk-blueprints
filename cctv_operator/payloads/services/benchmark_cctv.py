#!/usr/bin/env python3
"""Export stage metrics, or run an opt-in labeled person-detector comparison."""

import argparse
import json
import sys
from pathlib import Path

for ancestor in Path(__file__).resolve().parents:
    if (ancestor / "domain").is_dir():
        sys.path.insert(0, str(ancestor))
        break

from domain.benchmarks import Benchmarks
from domain.benchmark_replay import replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    summary = commands.add_parser("summary")
    summary.add_argument("--run-dir", required=True, type=Path)
    summary.add_argument("--output", type=Path)
    compare = commands.add_parser("replay")
    compare.add_argument("--dataset", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument("--models", nargs="+", choices=["small", "medium"], default=["small", "medium"])
    compare.add_argument("--threshold", type=float, default=.55)
    compare.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()
    if args.command == "summary":
        if not (args.run_dir / "benchmarks" / "stages.sqlite3").is_file():
            parser.error("the run has no stage measurements; use a run produced by the redesigned pipeline")
        result = Benchmarks(args.run_dir).summary()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        else:
            print(json.dumps(result, indent=2))
    else:
        if not 0 <= args.warmup <= 100:
            parser.error("--warmup must be between 0 and 100")
        replay(args.dataset, args.output, args.models, threshold=args.threshold, warmup=args.warmup)
        print(f"Comparison saved to {args.output / 'comparison.json'}")


if __name__ == "__main__":
    main()
