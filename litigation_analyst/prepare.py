#!/usr/bin/env python3
"""Prepare the published engine and optional EMC2 sample for a Docker worker run."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'payloads'))
from domain.sample_data import prepare_emc2
from mn_graph_analysis_skill.release import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-folder', type=Path)
    parser.add_argument('--target', choices=['aarch64-unknown-linux-gnu', 'x86_64-unknown-linux-gnu'], default='aarch64-unknown-linux-gnu' if platform.machine() in {'arm64', 'aarch64'} else 'x86_64-unknown-linux-gnu')
    args = parser.parse_args()
    if args.input_folder is not None:
        folder = args.input_folder.expanduser().resolve()
        if not folder.is_dir():
            parser.error('--input-folder must be an existing directory')
    else:
        folder = prepare_emc2(ROOT / 'prepared/emc2')
    engine = ROOT / 'payloads/docker_worker/engine'
    if not engine.exists():
        prepare(engine, args.target)
        (engine / 'target.txt').write_text(args.target)
    elif not (engine / 'target.txt').is_file() or (engine / 'target.txt').read_text() != args.target:
        raise ValueError('prepared engine target does not match; remove the generated engine directory and prepare again')
    wheels = ROOT / 'payloads/docker_worker/python_dependencies'
    wheels.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(wheels), '-r', str(ROOT / 'payloads/requirements.txt')], check=True, timeout=300)
    result = ROOT / 'prepared/inputs.json'
    result.parent.mkdir(exist_ok=True)
    result.write_text(json.dumps({'input_folder': str(folder)}, indent=2)+'\n')
    print(f'Prepared {args.target}. Input folder: {folder}')
    print('Run: MN_USE_LOCAL_SKILLS=1 mn blueprint run ./')
    if args.input_folder is not None:
        import shlex
        print('Custom folder: MN_USE_LOCAL_SKILLS=1 mn blueprint run ./ --set ' + shlex.quote('inputs.payload.input_folder=' + str(folder)))
    print('With no run input, the worker prepares its own pinned EMC2 copy.')
    print(f'To select the prepared or custom input folder, use {result} through your launcher input configuration.')


if __name__ == '__main__':
    main()
