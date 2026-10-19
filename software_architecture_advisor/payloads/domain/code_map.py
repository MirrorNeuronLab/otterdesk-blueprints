"""Architecture map shell and deterministic Markdown brief."""
import html
import hashlib
from pathlib import Path
import re
from mn_web_report_skill import asset_bytes, write_assets


def _code(value):
    value = str(value).replace('\r', r'\r').replace('\n', r'\n').replace('|', '&#124;')
    fence = '`' * (max([len(s) for s in re.findall(r'`+', value)] + [0]) + 1)
    return fence + ' ' + value + ' ' + fence


def brief(facts, history):
    c = facts['coverage']; h = history['coverage']
    lines = ['# Component and function evolution review', '',
        '[Open the interactive code map](../web/code-map.html) · [Static graph data](../data/static-code.json) · [Function history data](../data/function-evolution.json)', '',
        f"Captured {c['files']} files; extracted {len(facts['functions'])} functions and {len(facts['component_edges'])} file dependency edges with zero model calls.",
        f"Parser coverage: {c['status_counts']}. Unresolved call sites: {c['unresolved_calls']}.", '',
        'Components below are source files. The interactive views show file and function relationships. Calls are syntax/name candidates; include and call edges remain separate.', '',
        '## Where to inspect first', '', '| Component | Direct dependents | Direct dependencies | Functions |', '| --- | ---: | ---: | ---: |']
    for row in sorted(facts['components'], key=lambda r:(-r['fan_in']-r['fan_out'],r['id']))[:12]:
        lines.append(f"| {_code(row['id'])} | {row['fan_in']} | {row['fan_out']} | {row['functions']} |")
    lines += ['', 'Use the map to inspect edge evidence, direct callers/callees and source locations before deciding whether a boundary needs to change.', '',
              '## Function development over time', '', f"History status: {history['status']}. Anchor: `{history.get('revision','unavailable')}`.",
              f"Observed {len(history['events'])} function changes in {h.get('commits_with_file_diffs','unavailable')} first-parent commits; the configured window is {h.get('commit_limit','unavailable')} commits.", '',
              '| Function | Observed changes |', '| --- | ---: |']
    for row in history['hotspots'][:12]:
        lines.append(f"| {_code(row['function'])} | {row['changes']} |")
    lines += ['', 'Scrub or play the Git timeline to see the component and function graphs at each commit. Compare a baseline, inspect added/removed call candidates, and open exact definition evidence. Partial parse gaps remain unknown.', '',
              '## Limits and next checks', '', *['- '+s for s in facts['limitations']+history.get('limitations',[])]]
    if history.get('reason'):
        lines.append('- '+history['reason'])
    if h.get('gaps'):
        lines.append(f"- {len(h['gaps'])} historical parse gaps are retained in function-evolution.json; those files are not counted as unchanged.")
    if h.get('omitted_pair_commits'):
        lines.append(f"- Co-change pairs omit {len(h['omitted_pair_commits'])} commits that exceeded the pair budget.")
    lines += ['- Degree and churn rank inspection candidates. They do not measure severity, production failures or team ownership.',
              '- Verify important indirect calls and preprocessing branches with the actual build configuration; run targeted tests before proposing changes.', '']
    return '\n'.join(lines)


def render(*, data_root='../data', assets='assets', home='index.html', reports='../reports', register='review-register.html'):
    """A reusable HTML shell; all repository and review content stays in JSON."""
    asset_root = Path(__file__).with_name('workspace_assets')
    template = asset_root.joinpath('code-map.html').read_text()
    # One local SVG sprite supplies both static and dynamically rendered controls.
    # Inline fragments keep saved/file-open reports independent of icon requests.
    if '@REPORT_ICONS@' in template:
        template = template.replace('@REPORT_ICONS@',
            asset_root.joinpath('vendor/lucide-sprite.svg').read_text())
    # Retained shells share assets. A content identity prevents a browser from
    # combining a refreshed shell with a cached, incompatible script or style.
    template = re.sub(r'((?:src|href)="@ASSETS@/([^"?]+))"',
        lambda match: match[1] + '?v=' + hashlib.sha256(
            (asset_root.joinpath(match[2]).read_bytes() if asset_root.joinpath(match[2]).is_file()
             else asset_bytes(match[2]))).hexdigest()[:12] + '"', template)
    return (template.replace('../data/', html.escape(data_root, quote=True)+'/')
        .replace('../reports', html.escape(reports, quote=True)).replace('index.html', html.escape(home, quote=True))
        .replace('@DATA_ROOT@', html.escape(data_root, quote=True)).replace('@ASSETS@', html.escape(assets, quote=True))
        .replace('@REGISTER@', html.escape(register, quote=True)))


def publish_shell(root):
    from .workspace_history import atomic
    root = Path(root)
    assets = Path(__file__).with_name('workspace_assets')
    write_assets(root / 'web/assets')
    for name in ('code-map.js', 'code-map.css', 'report-shell.css', 'report-shell.js', 'overview-model.js', 'architecture-viz.js', 'graph-evolution.js', 'graph-layout.js', 'network-graph.js', 'comparison-presentation.js', 'code-paths.js', 'data-loader.js'):
        atomic(root / 'web/assets' / name, (assets/name).read_bytes())
    for source in (assets / 'vendor').iterdir():
        if source.suffix == '.md':
            continue
        atomic(root / 'web/assets/vendor' / source.name, source.read_bytes())
    atomic(root / 'web/code-map.html', render().encode())
