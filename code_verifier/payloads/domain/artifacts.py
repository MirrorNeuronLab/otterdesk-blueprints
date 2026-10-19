"""Run-scoped, atomic artifacts. Core owns delivery to configured host folders."""
import json
from pathlib import Path

from mn_sdk.blueprint_support import write_json
from mn_sdk.step_runtime import artifact_reference


def save(context, name, value):
    write_json(Path(context['run_dir']) / name, value)
    return artifact_reference(Path(name).stem, name)


def read(context, name):
    return json.loads((Path(context['run_dir']) / name).read_text(encoding='utf-8'))


def text(context, name, value):
    target = Path(context['run_dir']) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(value, encoding='utf-8')
    temporary.replace(target)
    return artifact_reference(target.stem, name)
