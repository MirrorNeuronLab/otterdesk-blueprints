#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path


DEFAULT_URL = "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/people-detection.mp4"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a looping sample MP4 for the door monitor demo.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "samples" / "door-demo.mp4",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(args.url, timeout=60) as response:
        with args.output.open("wb") as handle:
            shutil.copyfileobj(response, handle)

    print(args.output)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"failed to download sample video: {exc}", file=sys.stderr)
        raise
