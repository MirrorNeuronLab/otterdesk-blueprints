"""A self-contained, read-only replay of recorded simulation observations."""

import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'web_assets'


def render(final, trace):
    page = (ASSETS / 'index.html').read_text()
    data = json.dumps({'result': final, 'trace': trace}, ensure_ascii=True, allow_nan=False)
    data = data.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    page = page.replace('<link rel="stylesheet" href="style.css">', '<style>' + (ASSETS / 'style.css').read_text() + '</style>')
    page = page.replace('<iframe id="visualizer" title="PyLabRobot visualizer" src="visualizer/index.html"></iframe>', '')
    return page.replace('<script src="app.js" defer></script>',
                        '<script type="application/json" id="replay-data">' + data + '</script>\n<script type="module">' +
                        (ASSETS / 'app.js').read_text() + '</script>')
