#!/usr/bin/env python3
"""Download the optional pinned EMC2 sample; runtime dependencies are skill-owned."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "payloads"))
from domain.sample_data import prepare_emc2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-folder", type=Path)
    args = parser.parse_args()
    folder = args.input_folder.expanduser().resolve() if args.input_folder else prepare_emc2(ROOT / "prepared/emc2")
    if not folder.is_dir():
        parser.error("--input-folder must be an existing directory")
    result = ROOT / "prepared/inputs.json"
    result.parent.mkdir(exist_ok=True)
    result.write_text(json.dumps({"input_folder": str(folder)}, indent=2) + "\n")
    print(f"Sample input ready: {folder}")
    print("Runtime dependencies are prepared automatically from declared skills.")


if __name__ == "__main__":
    main()
