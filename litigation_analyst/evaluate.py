"""Run offline acceptance checks after a manual test; never invokes a model."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "payloads"))
from domain.evaluation import evaluate

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--human-review", type=Path)
    args = parser.parse_args()
    result = evaluate(args.run, args.expected, args.human_review)
    print(json.dumps(result, indent=2))
    sys.exit(1 if result["acceptance"] == "failed" else 0)
