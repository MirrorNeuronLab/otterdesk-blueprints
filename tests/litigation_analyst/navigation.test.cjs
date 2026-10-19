const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assets = path.resolve(__dirname, '../../litigation_analyst/payloads/domain/workspace_assets');
const scripts = ['navigation.js','workspace.js','reading.js'].map(name=>readFileSync(path.join(assets,name),'utf8')).join('\n');

function fixture() {
  const source={source_id:'case:notice.eml',relative_path:'notice.eml',media_type:'message/rfc822',text:'Source text',
    content_sha256:'source-hash',original_sha256:'original-hash',original_included:false,extraction_status:'Readable',review_state:'Awaiting review'};
  const finding={id:'F1',title:'Draft finding',assessment:'Review the source.',supporting_evidence:['E1'],counter_evidence:[],
    evidence_ids:['E1'],review_history:[],review_state:'AI draft',material_digest:'basis',revision:1,alternatives:[],
    source_basis:'Model assessment',model_review:'Not attorney review',limitations:'Verify original.'};
  return {title:'Test matter',snapshot_id:'snapshot',matter_id:'matter',goal:'Review the supplied records.',sources:[source],
    evidence:[{evidence_id:'E1',source_id:source.source_id,text:'Source text',content_sha256:'source-hash',start_offset:0,end_offset:11}],
    findings:[finding],issues:[],gaps:[],counsel_issues:[],reading_tasks:[],reading_review:{withheld_finding_ids:[],checks:[]},
    reading_reports:[{id:'counsel-brief',title:'Counsel review brief',filename:'brief.md',markdown:'# Brief'}],
    financial_review:{events:[],transactions:[]},matter_scope:{parties:[],intended_decision:'Review the records.'},
    graph:{nodes:[],edges:[],path_index:{},definition:'Source relationships',coverage:'Partial'},
    temporal:{events:[],nodes:[],count_definition:'Distinct messages',message_count:{count:0,unresolved_multiplicity:[]},source_record_count:0},
    coverage:{readable_ids:[source.source_id]},analysis:{status:'Draft for review',scope:'Frozen sources',stop_reason:'completed'},
    changes:{mode:'Single snapshot',previous_snapshot:null,items:[]},privacy:{},capabilities:{},audience:'Matter owner'};
}
function app(workspace=fixture()) {
  const listeners={}, elements=new Map(), downloads=[], shell={};
  const element = id => {
    if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',open:false,
      close(){this.open=false;},showModal(){this.open=true;},querySelector(){return null;}});
    return elements.get(id);
  };
  element('workspace-data').textContent=JSON.stringify(workspace);
  const document={getElementById:element,querySelector(){return null;},addEventListener(type,handler){(listeners[type]??=[]).push(handler);}};
  const MNWebReport={createReport(config){shell.config=config;return {setView(view){shell.view=view;},enhance(){},ready(){},setInspectorOpen(){},openInspector(){},closeInspector(){}};}};
  const ctx=vm.createContext({document,MNWebReport,window:{addEventListener(){}},location:{hash:''},Intl,Map,Set,
    crypto:{randomUUID:()=> 'test-review'},prompt:()=> 'Saved comparison',navigator:{}});
  vm.runInContext(scripts,ctx);
  ctx.captureDownload=(name,data)=>downloads.push({name,data});
  vm.runInContext('download=captureDownload; pageFor=data=>JSON.stringify(data);',ctx);
  return {ctx,elements,element,downloads,shell,html:()=>element('app').innerHTML,
    go(route){vm.runInContext(`goto({view:${JSON.stringify(route)}});render();`,ctx);},
    async click(action,id='') {
      const event={target:{closest:()=>({dataset:{action,id}})}};
      for(const handler of listeners.click||[])await handler(event);
    },
    async search(value) {
      element('document-query').value=value;
      for(const handler of listeners.submit||[])await handler({target:{id:'document-search'},preventDefault(){}});
      vm.runInContext('render()',ctx);
    }};
}

test('All original routes and saved views highlight one of eight primary groups',async()=>{
  const a=app();
  const groups={'Overview':'Overview','Findings':'Findings','Issues & evidence':'Questions','Evidence Explorer':'Evidence',
    'Comparisons':'Evidence','People & relationships':'People & events','Chronology':'Timeline','Reports':'Reports',
    'Work product':'Reports','Since last review':'Review history','Activity & audit':'Review history'};
  for(const [route,label] of Object.entries(groups)) {
    a.go(route);
    const tab=a.shell.config.tabs.find(row=>row[1]===label);
    assert.ok(tab);assert.equal(a.shell.view,tab[0]);
  }
  a.go('Matter settings');
  assert.equal(a.shell.view,'Matter settings');
  assert.equal(a.shell.config.tabs.length,9);
  await a.click('save-view');
  a.go('Overview');
  await a.click('open-view','0');
  assert.equal(vm.runInContext('state.view',a.ctx),'Matter settings');
});

test('Facts precede counts, flagged claims remain actionable and cannot become briefing eligible',()=>{
  const w=fixture();
  w.financial_review={transactions:[{transaction_ref:'TX1',currency:'USD',ledger_id:'ledger',request_minus_approval:'4500.00',posting_reversal_net:'0.00',qualification:'Accounting only.'}],
    events:[{transaction_ref:'TX1',currency:'USD',ledger_id:'ledger',event_type:'approved',amount:'8000.00',evidence_ids:['E1']}]};
  w.reading_review={withheld_finding_ids:['F1'],checks:[{finding_id:'F1',evidence_ids:['E1'],reason:'An approval record is present.'}]};
  const a=app(w);
  assert.ok(a.html().indexOf('USD 8,000.00')<a.html().indexOf('overview-counts'));
  assert.match(a.html(),/1 finding needs review/);
  assert.doesNotMatch(a.html(),/data-action="export-preview"/);
  a.go('Findings');
  assert.match(a.html(),/Needs attention/);
  assert.match(a.html(),/Original draft and review reason/);
  assert.doesNotMatch(a.html(),/No findings match/);
  a.go('Reports');
  assert.match(a.html(),/0 reviewed findings eligible/);
  assert.doesNotMatch(a.html(),/data-action="export-preview"/);
});

test('Evidence search is adjacent to documents and technical metadata stays in details',async()=>{
  const w=fixture();w.sources[0].relative_path='A very long document name '.repeat(40)+'.eml';
  const a=app(w);a.go('Evidence Explorer');
  assert.ok(a.html().indexOf('id="document-search"')<a.html().indexOf('class="document-table"'));
  assert.match(a.html(),/title="A very long document name/);
  assert.match(a.html(),/<details class="document-details">[\s\S]*Normalized SHA-256/);
  await a.search('no matching phrase');
  assert.equal(vm.runInContext('state.query',a.ctx),'no matching phrase');
  assert.match(a.html(),/No documents match these filters/);
  await a.click('reset');vm.runInContext('render()',a.ctx);
  assert.match(a.html(),/class="document-title"/);
});

test('Graph selection preserves other nodes and links while highlighting the selected neighborhood',()=>{
  const w=fixture();
  w.case_map={definition:'Source-backed graph',omitted_communications:0,omitted_financial_records:0,
    nodes:['a','b','c','d'].map(id=>({id,label:id,kind:'correspondent',source_ids:['case:notice.eml'],evidence_ids:['E1'],qualification:'Identity unresolved'})),
    edges:[{source:'a',target:'b',label:'Header',evidence_ids:['E1']},{source:'c',target:'d',label:'Header',evidence_ids:['E1']}]};
  const a=app(w);a.go('People & relationships');
  const before=(a.html().match(/data-action="map-node" data-id="[abcd]"/g)||[]).length;
  vm.runInContext('state.mapSelection="a";render()',a.ctx);
  assert.equal((a.html().match(/data-action="map-node" data-id="[abcd]"/g)||[]).length,before);
  assert.match(a.html(),/muted-node/);assert.match(a.html(),/highlighted/);
  assert.match(a.html(),/aria-label="Selected graph item"/);
});

test('Review edits show a save reminder and the downloaded snapshot retains them',async()=>{
  const a=app();
  for(const [id,value] of Object.entries({'review-actor':'Test reviewer','review-text':'Qualified observation',
    'review-rationale':'Read the source','review-action':'Reviewed with qualification'}))a.element(id).value=value;
  await a.click('commit-review','F1');
  assert.match(a.html(),/Unsaved review changes/);
  a.go('Reports');assert.match(a.html(),/1 reviewed finding eligible/);
  await a.click('save-copy');
  assert.match(a.html(),/Copy download requested/);
  const saved=JSON.parse(a.downloads.at(-1).data);
  assert.equal(saved.decisions[0].text,'Qualified observation');
  const reopened=app(saved);
  assert.doesNotMatch(reopened.html(),/Unsaved review changes|Copy download requested/);
});

test('Empty matters render every primary destination without exposing unavailable actions',()=>{
  const w=fixture();
  w.sources=[];w.evidence=[];w.findings=[];w.coverage.readable_ids=[];
  const a=app(w);
  for(const route of ['Overview','Findings','Issues & evidence','Evidence Explorer','People & relationships','Chronology','Reports','Activity & audit'])a.go(route);
  a.go('Evidence Explorer');assert.match(a.html(),/No documents are included/);
  a.go('Overview');assert.match(a.html(),/>Read report</);
});
