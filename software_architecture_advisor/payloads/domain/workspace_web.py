"""Offline dashboard rendering from retained real analysis records."""
import base64
import hashlib
import html
import json
from pathlib import Path
import shutil

from mn_sdk.step_runtime import artifact_reference
from .workspace_projection import project
from .workspace_history import atomic, json_bytes, retain, storage
from .improvement_prompts import markdown as prompts_markdown
from .catalog_store import CatalogStore


def render(workspace, index, *, historical=False):
    assets = Path(__file__).with_name('workspace_assets')
    script = (assets / 'workspace.js').read_text(encoding='utf-8')
    style = (assets / 'workspace.css').read_text(encoding='utf-8')
    payload = json.dumps({'workspace': workspace, 'index': index, 'historical': historical},
        ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('&', '\\u0026')
    sha = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = f"default-src 'none'; script-src 'sha256-{sha}'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}">'
        '<title>Architecture investigation · OtterDesk</title>'
        f'<style>{style}</style></head><body><a class="skip" href="#content">Skip to investigation</a>'
        '<div id="app"></div><dialog id="details"></dialog><p id="notice" role="status" aria-live="polite"></p>'
        f'<script id="analysis-data" type="application/json">{payload}</script><script>{script}</script></body></html>')


def publish(context, report, registers, *, workspace=None):
    root = Path(context['run_dir'])
    projected = workspace if workspace is not None else project(context, report, registers)
    CatalogStore(root).write('improvement_prompts.json', projected['improvement_prompts'])
    document = ('# Architecture improvement handoffs\n\n' + prompts_markdown(projected)).encode('utf-8')
    target = root / 'improvement_prompts.md'
    if target.exists() and target.read_bytes() != document:
        raise ValueError('Improvement prompt document changed on replay')
    atomic(target, document)
    workspace, index, store = retain(context, projected)
    # Web is a required deliverable. Rendering errors are explicit after durable data.
    with storage(context) as (store, _):
        index = json.loads((store / 'data/index.json').read_text())
        web = store / 'web'
        own = web / 'snapshots' / (workspace['id'] + '.html')
        if not own.exists():
            atomic(own, render(workspace, index, historical=True).encode('utf-8'))
        latest = json.loads((store / 'data/workspace.json').read_text())
        atomic(web / 'index.html', render(latest, index).encode('utf-8'))
        shutil.copytree(store / 'data', root / 'data', dirs_exist_ok=True)
        shutil.copytree(web, root / 'web', dirs_exist_ok=True)
    page = (root / 'web/index.html').resolve()
    handle = {'kind': 'output', 'adapter': 'static_html', 'title': 'Architecture investigation',
        'path': str(page), 'url': page.as_uri(), 'metadata': {'renderer': 'static_html',
        'snapshot': latest['snapshot_id'], 'publication': latest['id'], 'read_only_source': True}}
    atomic(root / 'web_ui.json', json_bytes(handle))
    refs = [artifact_reference('architecture_workspace', 'data/workspace.json'),
        artifact_reference('architecture_history', 'data/index.json'),
        artifact_reference('architecture_dashboard', 'web/index.html'),
        artifact_reference('web_ui_handle', 'web_ui.json'),
        artifact_reference('architecture_snapshot_workspace', 'data/snapshots/' + workspace['id'] + '/workspace.json'),
        artifact_reference('improvement_prompts', 'improvement_prompts.md'),
        artifact_reference('improvement_prompt_data', 'improvement_prompts.json')]
    return {'snapshot': workspace['id'], 'data': refs[4], 'latest_data': refs[0], 'web': refs[2]}, refs
