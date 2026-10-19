const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const assets = path.resolve(__dirname, '../../litigation_analyst/payloads/domain/workspace_assets');
const base = readFileSync(path.join(assets, 'workspace.js'), 'utf8');
const reading = readFileSync(path.join(assets, 'reading.js'), 'utf8');
function context(workspace = {}) {
  const captured = [];
  const document = {addEventListener() {}, getElementById(id) {
    return id === 'workspace-data' ? {textContent: JSON.stringify(workspace)} : {value:'Authorized test reviewer', close() {}};
  }};
  const ctx = vm.createContext({document, captured, Intl, Map, Set,
    notice() {}, download(name, data) {captured.push(JSON.parse(data));}, pageFor: JSON.stringify});
  vm.runInContext(base.slice(0, base.indexOf('const sourceById')), ctx);
  for(const prefix of ['const empty =', 'const table =']) {
    vm.runInContext(base.split('\n').find(line=>line.startsWith(prefix)), ctx);
  }
  vm.runInContext('const evidenceById = new Map((W.evidence || []).map(p=>[p.evidence_id,p]));', ctx);
  vm.runInContext(reading, ctx);
  return ctx;
}

test('Markdown renders tables, quotes and internal citations while HTML/URLs stay inert', () => {
  const ctx = context({evidence:[{evidence_id:'verified-id'}]});
  const rendered = ctx.renderMarkdown('# Brief\n\n| Record | Meaning |\n| --- | --- |\n| A | x\\|y |\n\n> Exact quotation\n\n[Source](evidence:verified-id)\n\n<script>alert(1)</script>\n[unsafe](javascript:alert(1))');
  assert.match(rendered, /<table>/);
  assert.match(rendered, /x\|y/);
  assert.match(rendered, /<blockquote>Exact quotation/);
  assert.match(rendered, /data-action="evidence" data-id="verified-id"/);
  assert.match(ctx.renderMarkdown('[Source](exact-source-passages.md#verified-id)'), /data-action="evidence"/);
  assert.doesNotMatch(rendered, /<script>|href=|<img/);
  assert.match(rendered, /&lt;script&gt;/);
  assert.doesNotMatch(vm.runInContext(`money('12500', '<img src=x onerror=alert(1)>')`, ctx), /<img/);
  assert.equal(ctx.money('9007199254740993.123','USD'),'USD 9,007,199,254,740,993.123');
});

test('A conflicting draft cannot become approved through local review or leak reading data into a briefing', () => {
  const f = id => ({id,material_digest:id,title:id,assessment:id,revision:1,limitations:'Verify originals',
    supporting_evidence:['verified-id'],counter_evidence:[],review_history:[{actor:'Test reviewer',
      action:'Reviewed with qualification',material_digest:id,text:'Qualified wording',rationale:'Reviewed source',finding_id:id}]});
  const ctx = context({findings:[f('clear'),f('blocked')],sources:[{source_id:'case:visible',text:'Full source',original_included:true}],
    evidence:[{evidence_id:'verified-id',source_id:'case:visible'}],graph:{nodes:[],edges:[]},temporal:{},capabilities:{},
    analysis:{stop_reason:'completed'},reading_review:{withheld_finding_ids:['blocked']},
    reading_reports:[{markdown:'UNREVIEWED_REPORT_MARKER'}],reading_tasks:[{title:'UNREVIEWED_TASK_MARKER'}],
    consistency:{checks:[{reason:'UNREVIEWED_CHECK_MARKER'}]},case_map:{private:'UNREVIEWED_GRAPH_MARKER'}});
  vm.runInContext(`let decisions=[]; let state={}; const defaults={};
    function visibleFindings(){return W.findings;}`, ctx);
  vm.runInContext(base.split('\n').find(line=>line.startsWith('function currentReview(')),ctx);
  vm.runInContext(base.slice(base.indexOf('function briefing() {'),base.indexOf('\ndocument.addEventListener("click"')),ctx);
  vm.runInContext('briefing()',ctx);
  assert.equal(ctx.captured[0].findings.length,1);
  assert.equal(ctx.captured[0].findings[0].id,'clear');
  assert.equal(ctx.captured[0].sources[0].text,null);
  assert.equal(ctx.captured[0].sources[0].original_included,false);
  assert.doesNotMatch(JSON.stringify(ctx.captured[0]),/UNREVIEWED_/);
});
