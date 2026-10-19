"""The reusable report shell's disclosure and keyboard contracts."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import shutil
import subprocess
import pytest
from mn_web_report_skill import asset_bytes
from workspace_paths import companion_workspace
SHARED_UI=companion_workspace(Path(__file__).parents[2])/"mn-skills/web_report_skill/frontend"

ASSETS=Path(__file__).parents[2]/'software_architecture_advisor/payloads/domain/workspace_assets'


@pytest.fixture(autouse=True)
def offline_text_memory():
    """Pure presentation tests do not use the suite's TextMemory transport."""
    yield

class Shell(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.path=[];self.header_actions=[];self.primary_tabs=[];self.extra_tabs=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id'):self.ids.append(attrs['id'])
        if tag in ('button','a') and any(t=='header' for t,_ in self.path):
            self.header_actions.append(any(a.get('id')=='report-actions' for _,a in self.path))
        if attrs.get('role')=='tab':
            target=self.extra_tabs if any(a.get('id')=='more-views' for _,a in self.path) else self.primary_tabs
            target.append(attrs['id'])
        if tag not in ('input','meta','link','br','hr','img'):
            self.path.append((tag,attrs))
    def handle_endtag(self,tag):
        for i in range(len(self.path)-1,-1,-1):
            if self.path[i][0]==tag:
                self.path=self.path[:i];return

def test_component_mounts_and_header_actions_have_one_quiet_entry_point():
    page=(ASSETS/'code-map.html').read_text();shell=Shell();shell.feed(page)
    assert len(shell.ids)==len(set(shell.ids))
    assert 'brand-mark' not in page and 'class="brand"' not in page
    assert {'report-actions','report-navigation','report-inspector-ui','evidence-tables'} <= set(shell.ids)
    assert 'data-report-href="../reports/report.md"' in page
    assert page.index('@ASSETS@/report-ui.js') < page.index('@ASSETS@/report-shell.js') < page.index('@ASSETS@/code-map.js')
    source=(SHARED_UI/'src/main.tsx').read_text()
    for name in ('DropdownMenu','Tooltip','Tabs','Collapsible','Popover','Sheet','Input','NativeSelect','Textarea','Button'):
        assert './components/ui/'+{'DropdownMenu':'dropdown-menu','NativeSelect':'native-select'}.get(name,name.lower()) in source
    assert re.search(r'<Sheet\s+modal=\{false\}',source)


def test_actual_component_keyboard_and_evidence_contracts():
    node=shutil.which('node');ui=ASSETS.parents[2]/'report_ui'
    if not node or not (ui/'node_modules/jsdom').exists():
        pytest.skip('Run npm ci in report_ui for the declared component test dependencies')
    subprocess.run([node,'--test','test/components.test.mjs'],cwd=ui,
                   check=True,capture_output=True,text=True,timeout=20)


def test_compiled_component_assets_match_their_declared_sources():
    ui=SHARED_UI
    receipt=json.loads(asset_bytes('vendor/report-components-provenance.txt'))
    assert receipt['stack']=='shadcn/ui + Radix UI + React + Lucide'
    for relative,digest in receipt['sources'].items():
        assert hashlib.sha256((ui/relative).read_bytes()).hexdigest()==digest,relative
    for relative,digest in receipt['outputs'].items():
        assert hashlib.sha256(asset_bytes(relative)).hexdigest()==digest,relative
    assert len(receipt['registry'])==10
    assert all(row['url'].startswith('https://ui.shadcn.com/r/') for row in receipt['registry'].values())


def test_published_geist_foundation_and_fonts_are_pinned_and_offline():
    """An exported report must carry its actual UI dependency, not a CDN theme."""
    vendor=ASSETS/'vendor'
    receipt=json.loads(asset_bytes('vendor/geist-provenance.txt'))
    assert receipt['vercel-brand.css']['source']=='https://vercel.com/geist/vercel-brand.css'
    assert receipt['vercel-brand.css']['sha256']=='e4f4f41f48947fbb24f4eb49cab37cb077a04af656f746388a9052c1c7f1330e'
    for name,item in receipt.items():
        assert hashlib.sha256(asset_bytes('vendor/'+name)).hexdigest()==item['sha256']
        if name.endswith('.woff2'):
            assert asset_bytes('vendor/'+name)[:4]==b'wOF2'
            assert item['version']=='1.8.1'
    assert 'SIL OPEN FONT LICENSE' in asset_bytes('vendor/geist-LICENSE.txt').decode()
    fonts=asset_bytes('report-fonts.css').decode()
    assert 'https:' not in fonts and '@import' not in fonts
    assert 'Geist-Variable.woff2' in fonts and 'GeistMono-Variable.woff2' in fonts
    page=(ASSETS/'code-map.html').read_text()
    assert 'class="report vbg-report"' in page
    assert 'font-src \'self\' file:' in page
    assert '@ASSETS@/report-components.css' in page
    assert '--vbg-surface-primary' in asset_bytes('report-components.css').decode()
    assert '@ASSETS@/report-fonts.css' in page
    assert 'data-variant="primary"' in (ASSETS/'code-map.js').read_text()


def test_icon_controls_have_names_and_all_local_fragments_resolve():
    from domain.code_map import render
    page=render()
    assert '@REPORT_ICONS@' not in page
    sprite=ASSETS/'vendor/lucide-sprite.svg'
    receipt=json.loads((ASSETS/'vendor/lucide-provenance.txt').read_text())
    assert receipt['package']=='lucide-static' and receipt['version']=='1.59.0'
    assert hashlib.sha256(sprite.read_bytes()).hexdigest()==receipt['sprite_sha256']
    symbols={node.attrib['id'] for node in ET.fromstring(sprite.read_text())
             if node.tag.endswith('symbol')}
    assert len(symbols)==15
    assert all(ref in symbols for ref in re.findall(r'<use href="#([^"]+)"',page))
    assert not any(token in sprite.read_text() for token in ('<script','<style','href=','url('))
    assert 'ISC License' in (ASSETS/'vendor/lucide-LICENSE.txt').read_text()
    parsed=Shell();parsed.feed(page)
    assert len(parsed.ids)==len(set(parsed.ids))
    component_source=(SHARED_UI/'src/main.tsx').read_text()+(ASSETS.parents[2]/'report_ui/src/main.tsx').read_text()
    for name in ('Actions','Close details panel','Previous commit','Next commit'):
        assert f'aria-label="{name}"' in component_source
    assert 'aria-hidden="true" focusable="false"' in page
    assert 'playbackLabel(false)' in (ASSETS/'code-map.js').read_text()
    assert 'playbackLabel(true)' in (ASSETS/'code-map.js').read_text()
