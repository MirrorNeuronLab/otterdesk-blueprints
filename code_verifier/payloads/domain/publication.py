"""Stage report artifacts in the SDK-provided output folder for host delivery."""
from pathlib import Path
import shutil
import tempfile


def stage_available_outputs(context):
    from mn_sdk.blueprint_support import source_manifest
    run = Path(context['run_dir'])
    artifacts = source_manifest(__file__)['contracts']['outputs']['artifacts']
    stage_outputs(context, [item['path'] for item in artifacts if (run / item['path']).exists()])


def stage_outputs(context, names):
    run = Path(context['run_dir']).resolve()
    output = Path(context.get('output_folder') or run).resolve()
    if output == run:
        return
    if run in output.parents:
        raise ValueError('Report staging and run directories must be separate.')
    for name in names:
        source = run / name
        if source.is_symlink() or not source.resolve().is_relative_to(run):
            raise ValueError('Report artifacts must remain inside the run directory.')
        if not source.exists():
            raise FileNotFoundError('A report artifact is missing.')
        if source.is_dir():
            (output / source.relative_to(run)).mkdir(parents=True, exist_ok=True)
        files = list(source.rglob('*')) if source.is_dir() else [source]
        if any(p.is_symlink() for p in files):
            raise ValueError('Report artifacts must not contain symlinks.')
        for path in files:
            if not path.is_file():
                continue
            target = output / path.relative_to(run)
            if not target.resolve().is_relative_to(output):
                raise ValueError('Staged artifacts must remain inside the output folder.')
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
            try:
                shutil.copyfile(path, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
