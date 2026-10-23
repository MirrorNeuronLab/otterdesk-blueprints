"""Capture authorized local source and knowledge; never import reviewed programs."""
import os
from pathlib import Path

from mn_code_search_skill import TextSearchIndex
from mn_static_code_analysis_skill import SUPPORTED_EXTENSIONS, analyze_sources
from mn_sdk.agent_events import report_activity
from mn_sdk.integrations.block_inputs import capture_declared_inputs

from .artifacts import read
from .configuration import BLUEPRINT_ID, settings

EXCLUDED = {'.git', '.svn', 'node_modules', 'vendor', 'dist', 'build', '.venv',
            'venv', '__pycache__', '.next', 'coverage', '.idea', '.vscode'}
TEXT_EXTENSIONS = SUPPORTED_EXTENSIONS | {'.md', '.txt', '.rst', '.json', '.yaml', '.yml',
                                        '.toml', '.ini', '.cfg', '.html', '.css', '.sql', '.sh'}


def capture_folder(root, *, max_files=2000, max_bytes=10_000_000):
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Choose a repository checkout or source folder.')
    sources, omitted, total, scanned = {}, [], 0, 0
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in sorted(folders):
            path = Path(directory) / name
            if name.casefold() in EXCLUDED or name.startswith('.') or path.is_symlink():
                omitted.append({'path': path.relative_to(root).as_posix(), 'reason': 'excluded_directory_or_symlink'})
        folders[:] = sorted(n for n in folders if not n.startswith('.') and n.casefold() not in EXCLUDED
                            and not (Path(directory) / n).is_symlink())
        scanned += len(files) + len(folders)
        if scanned > 30_000:
            raise ValueError('Source scan exceeds 30,000 entries; select a smaller folder.')
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if (path.is_symlink() or name.startswith('.') or path.suffix.lower() not in TEXT_EXTENSIONS
                    or name.casefold().startswith(('credentials', 'secrets', 'id_rsa', 'id_ed25519'))
                    or not path.is_file()):
                omitted.append({'path': relative, 'reason': 'excluded_format_secret_name_or_symlink'})
                continue
            size = path.stat().st_size
            if size > 500_000:
                omitted.append({'path': relative, 'reason': 'file_exceeds_500KB'})
                continue
            if len(sources) >= max_files or total + size > max_bytes:
                raise ValueError('Source capture budget exceeded; select a smaller folder.')
            data = path.read_bytes()
            if len(data) > 500_000 or total + len(data) > max_bytes:
                raise ValueError('Source grew beyond the capture budget.')
            try:
                value = data.decode('utf-8')
                if '\x00' in value:
                    raise ValueError('binary')
            except (UnicodeError, ValueError):
                omitted.append({'path': relative, 'reason': 'not_utf8_text'})
                continue
            sources[relative] = value
            total += len(data)
    return sources, omitted


def role(path):
    parts = Path(path).parts
    name = Path(path).name.casefold()
    if path.startswith('knowledge/') or Path(path).suffix.lower() in {'.md', '.rst', '.txt'}:
        return 'documentation'
    if any(p.casefold() in {'test', 'tests', '__tests__'} for p in parts) or any(
            token in name for token in ('test_', '.test.', '.spec.', '_test.')):
        return 'test_source'
    return 'implementation'


def capture(block, inputs):
    report_activity("Capturing source and documentation", owner_blueprint=BLUEPRINT_ID,
                    step_id=block.step_id, run_dir=block.store.run_dir)
    settings(block)
    if block.store.path("capture.json").is_file():
        value = read(block, "capture.json")
    else:
        value = capture_sources(block, inputs)
    sources = value["sources"]
    analysis = analyze_sources({p: v for p, v in sources.items() if Path(p).suffix in SUPPORTED_EXTENSIONS})
    block.store.path("source").mkdir(parents=True, exist_ok=True)
    for path, content in sources.items():
        block.check()
        block.store.commit_bytes("source/" + path, content.encode("utf-8"), kind="captured_source")
    capture_ref = block.store.commit("capture.json", value, kind="source_capture")
    analysis_ref = block.store.commit("static-analysis.json", analysis, kind="static_analysis")
    return {"snapshot_id": value["snapshot_id"], "files": len(sources),
            "capture": capture_ref.to_dict(), "static_analysis": analysis_ref.to_dict()}


def capture_sources(block, inputs):
    inputs = capture_declared_inputs(block, inputs, runtime_file=__file__)
    folder = inputs.get('input_folder')
    if not folder:
        raise ValueError('Choose a repository checkout or source folder.')
    root = Path(folder).resolve(strict=True)
    run_root = block.store.run_dir
    if run_root == root or run_root.is_relative_to(root):
        raise ValueError('Run outputs must be outside the inspected source folder.')
    sources, omitted = capture_folder(root)
    if any(p.startswith('knowledge/') for p in sources):
        # Keep repository paths separate from supervisor-owned blueprint knowledge.
        sources = {'repository/' + p: v for p, v in sources.items()}
        omitted = [{**item, 'path': 'repository/' + item['path']} for item in omitted]
    knowledge = block.job_directory / 'knowledge' / 'rules'
    custom = {}
    if knowledge.is_symlink() or knowledge.parent.is_symlink():
        raise ValueError('Job knowledge must not be a symlink.')
    if knowledge.is_dir():
        custom, skipped = capture_folder(knowledge, max_files=100, max_bytes=500_000)
        if skipped:
            raise ValueError('Custom rules must be bounded UTF-8 Markdown files without symlinks.')
        if any(Path(p).suffix.lower() != '.md' for p in custom):
            raise ValueError('Custom rules must be Markdown files.')
    sources.update({'knowledge/rules/' + p: v for p, v in custom.items()})
    index = TextSearchIndex(sources)
    docs = [p for p in sources if role(p) == 'documentation' and not p.startswith('knowledge/')]
    value = {'schema_version': 'mn.software_rules.capture.v1', 'sources': sources,
             'snapshot_id': index.snapshot_id, 'documents': docs,
             'custom_documents': ['knowledge/rules/' + p for p in custom], 'omitted': omitted,
             'source_execution': False}
    return value
