#!/usr/bin/env python3
"""Stage the published Linux graph engine and Python wheels for the Docker worker."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

from mn_graph_analysis_skill.release import prepare

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['aarch64-unknown-linux-gnu', 'x86_64-unknown-linux-gnu'],
        default='aarch64-unknown-linux-gnu' if platform.machine() in {'arm64', 'aarch64'} else 'x86_64-unknown-linux-gnu')
    args = parser.parse_args()
    engine = ROOT / 'payloads/docker_worker/engine'
    if not engine.exists():
        prepare(engine, args.target)
        (engine / 'target.txt').write_text(args.target)
    elif not (engine / 'target.txt').is_file() or (engine / 'target.txt').read_text() != args.target:
        raise ValueError('Prepared engine target differs; remove generated engine directory and prepare again')
    wheels = ROOT / 'payloads/docker_worker/python_dependencies'
    wheels.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(wheels),
        '-r', str(ROOT / 'payloads/docker_worker/provider-requirements.txt')], check=True, timeout=300)
    print(f'Prepared {args.target}. Supply repository_url or input_folder when launching the blueprint.')


if __name__ == '__main__':
    main()
