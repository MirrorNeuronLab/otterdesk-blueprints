"""External-data dashboards over append-only retained architecture records."""
import html
import json
from pathlib import Path
import shutil

from mn_sdk.step_runtime import artifact_reference
from .workspace_projection import project
from .workspace_history import atomic, json_bytes, retain, storage
from .improvement_prompts import markdown as prompts_markdown
from .catalog_store import CatalogStore
from .code_map import render as render_map
from mn_web_report_skill import write_assets
from mn_sdk_web_ui import static_run_report_handle
from .chat_summary import build as build_chat_summary


def render(workspace, index, *, historical=False):
    if workspace.get('static_analysis'):
        publication = workspace['id']
        page = render_map(data_root=('../../' if historical else '../')+'data/snapshots/'+publication,
            assets='../assets' if historical else 'assets',
            home='../snapshots/'+publication+'.html' if historical else 'index.html',
            reports=('../../' if historical else '../')+'reports/snapshots/'+publication,
            register='../reviews/'+publication+'.html' if historical else 'review-register.html')
    else:
        page = render_register(workspace, index, historical=historical)
    if not historical:
        page = page.replace('</head>', '<meta name="otterdesk-chat-summary" content="data/chat-summary.json"></head>', 1)
    return page


def render_register(workspace, index, *, historical=False):
    # Shells contain no source or review data. The same renderer serves every run.
    prefix = '../' if historical else ''
    data_root = ('../../data/snapshots/' if historical else '../data/snapshots/') + workspace['id']
    csp = "default-src 'none'; script-src 'self' file:; style-src 'self' file:; img-src data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'"
    map_path = '../maps/' + workspace['id'] + '.html' if historical else 'code-map.html'
    map_link = (f'<nav class="map-link"><a href="{html.escape(map_path, quote=True)}">Component and function evolution map</a></nav>'
                if workspace.get('static_analysis') else '')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="data-root" content="{html.escape(data_root, quote=True)}">'
        f'<meta name="historical" content="{str(historical).lower()}">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}">'
        '<title>Architecture investigation · OtterDesk</title>'
        f'<link rel="stylesheet" href="{prefix}assets/workspace.css">'
        f'<script defer src="{prefix}assets/data-loader.js"></script>'
        f'<script defer src="{prefix}assets/workspace.js"></script></head><body>'
        '<section id="load-data"><h1>Open the review workspace</h1><p id="load-status" role="status"></p>'
        '<label>Open workspace.json and index.json from this snapshot’s data folder '
        '<input id="data-files" type="file" accept=".json,application/json" multiple></label></section>'
        '<div id="content" hidden><a class="skip" href="#investigation">Skip to investigation</a>'
        + map_link + '<div id="app"></div><dialog id="details"></dialog>'
        '<p id="notice" role="status" aria-live="polite"></p></div></body></html>')


def publish(block, report, registers, *, workspace=None, review_file=None):
    root = Path(block.store.run_dir)
    projected = workspace if workspace is not None else project(block, report, registers)
    has_map = (root / 'data/static-code.json').is_file() and (root / 'data/function-evolution.json').is_file()
    if has_map:
        projected['static_analysis'] = {'code_map': 'code-map.html'}
    CatalogStore(root).write('data/improvement_prompts.json', projected['improvement_prompts'])
    document = ('# Architecture improvement handoffs\n\n' + prompts_markdown(projected)).encode('utf-8')
    target = root / 'reports/improvement_prompts.md'
    if target.exists() and target.read_bytes() != document:
        raise ValueError('Improvement prompt document changed on replay')
    atomic(target, document)
    workspace, index, _ = retain(block, projected, review_file=review_file)
    with storage(block) as (store, _):
        index = json.loads((store / 'data/index.json').read_text())
        web = store / 'web'
        assets = Path(__file__).with_name('workspace_assets')
        write_assets(web / 'assets')
        for name in ('workspace.js', 'workspace.css', 'code-map.js', 'code-map.css', 'report-shell.css', 'report-shell.js', 'overview-model.js', 'architecture-viz.js', 'graph-evolution.js', 'graph-layout.js', 'network-graph.js', 'comparison-presentation.js', 'code-paths.js', 'data-loader.js'):
            atomic(web / 'assets' / name, (assets/name).read_bytes())
        for source in (assets / 'vendor').iterdir():
            if source.suffix == '.md':
                continue
            atomic(web / 'assets/vendor' / source.name, source.read_bytes())
        # Shared assets and their shells are one presentation version. Refresh
        # every retained shell so an older template cannot load incompatible JS.
        # Authoritative JSON and Markdown retain their immutable identities.
        for entry in index['snapshots']:
            saved = json.loads((store / 'data/snapshots' / entry['id'] / 'workspace.json').read_text())
            page = render(saved, index, historical=True).encode('utf-8')
            atomic(web / 'snapshots' / (saved['id']+'.html'), page)
            if saved.get('static_analysis'):
                atomic(web / 'maps' / (saved['id']+'.html'), page)
            atomic(web / 'reviews' / (saved['id']+'.html'), render_register(saved, index, historical=True).encode())
        latest = json.loads((store / 'data/workspace.json').read_text())
        static_path = store / 'data/snapshots' / latest['id'] / 'static-code.json'
        static = json.loads(static_path.read_text()) if static_path.is_file() else None
        atomic(store / 'data/chat-summary.json', json_bytes(build_chat_summary(latest, static)))
        if latest.get('static_analysis'):
            atomic(web / 'code-map.html', render(latest, index).encode('utf-8'))
        atomic(web / 'index.html', render(latest, index).encode('utf-8'))
        atomic(web / 'review-register.html', render_register(latest, index).encode('utf-8'))
        shutil.copytree(store / 'data', root / 'data', dirs_exist_ok=True)
        shutil.copytree(web, root / 'web', dirs_exist_ok=True)
    handle = static_run_report_handle(root, 'web/index.html', title='Architecture review', optional=False)
    handle['metadata'].update(snapshot=latest['snapshot_id'], publication=latest['id'], read_only_source=True)
    atomic(root / 'web_ui.json', json_bytes(handle))
    refs = [artifact_reference('architecture_workspace', 'data/workspace.json'),
        artifact_reference('architecture_history', 'data/index.json'),
        artifact_reference('architecture_dashboard', 'web/index.html'),
        artifact_reference('web_ui_handle', 'web_ui.json'),
        artifact_reference('architecture_snapshot_workspace', 'data/snapshots/' + workspace['id'] + '/workspace.json'),
        artifact_reference('improvement_prompts', 'reports/improvement_prompts.md'),
        artifact_reference('improvement_prompt_data', 'data/improvement_prompts.json')]
    return {'snapshot': workspace['id'], 'data': refs[4], 'latest_data': refs[0], 'web': refs[2]}, refs
