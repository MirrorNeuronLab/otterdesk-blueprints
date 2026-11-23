const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assets = path.resolve(__dirname, '../../litigation_analyst/payloads/domain/workspace_assets');
const scripts = ['case_graph_model.js','case_graph_view.js','navigation.js','workspace.js','reading.js'].map(name=>readFileSync(path.join(assets,name),'utf8')).join('\n');

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

test('The dedicated graph and existing review routes select their navigation groups',async()=>{
  const a=app();
  const groups={'Overview':'Overview','Case graph':'Case graph','Findings':'Findings','Issues & evidence':'Questions','Evidence Explorer':'Evidence',
    'Comparisons':'Evidence','People & relationships':'People & events','Chronology':'Timeline','Reports':'Reports',
    'Work product':'Reports','Since last review':'Review history','Activity & audit':'Review history'};
  for(const [route,label] of Object.entries(groups)) {
    a.go(route);
    const tab=a.shell.config.tabs.find(row=>row[1]===label);
    assert.ok(tab);assert.equal(a.shell.view,tab[0]);
  }
  a.go('Matter settings');
  assert.equal(a.shell.view,'Matter settings');
  assert.equal(a.shell.config.tabs.length,10);
  await a.click('save-view');
  a.go('Overview');
  await a.click('open-view','0');
  assert.equal(vm.runInContext('state.view',a.ctx),'Matter settings');
});

test('The handoff asks one source-linked question and opens its existing review surface',async()=>{
  const w=fixture();
  w.supervision={next_review:{kind:'finding',finding_id:'F1',question:'How should this draft be qualified?',reason:'Compare both accounts.',
    timing:'Before relying on this finding',evidence_ids:['E1']},boundary:'Discussion is not approval.'};
  const a=app(w);
  assert.match(a.html(),/Your next review/);
  assert.match(a.html(),/How should this draft be qualified/);
  assert.equal((a.html().match(/data-action="finding" data-id="F1" class="primary"/g)||[]).length,1);
  assert.match(a.html(),/data-action="evidence" data-id="E1"/);
  await a.click('finding','F1');
  assert.equal(vm.runInContext('state.view',a.ctx),'Findings');
  w.findings[0].review_history=[{actor:'Reviewer',action:'Reviewed with qualification',material_digest:'basis',text:'Qualified wording',rationale:'Compared records',at:'2026-11-01T12:00:00Z'}];
  assert.doesNotMatch(app(w).html(),/How should this draft be qualified/);
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

test('Case graph distinguishes hypotheses, citations, copies and documented attribution',()=>{
  const w=fixture(), first=w.sources[0];
  const copy={...first,source_id:'case:copy.eml',relative_path:'archive/copy.eml'};
  const other={...first,source_id:'case:other.eml',content_sha256:'other-hash'};
  w.sources.push(copy,other);
  w.evidence.push({...w.evidence[0],evidence_id:'E2',source_id:copy.source_id});
  w.reading_review.withheld_finding_ids=['F1'];
  w.issues=[
    {id:'Q1',question:'Was notice sent?',supporting_evidence:['E1'],contradictory_evidence:['E2'],alternatives:['A later dispatch is possible.']},
    {id:'Q2',parent_id:'Q1',question:'When was it received?',supporting_evidence:['E1'],contradictory_evidence:[]}
  ];
  w.temporal.events=[{source_ids:[first.source_id],time:{earliest:null},fields:{headers:{From:['sender@example.test']}},
    evidence_refs:[{evidence_id:'E1'}],qualification:'Recorded header.'}];
  const a=app(w);
  assert.match(a.html(),/Explore case graph/);assert.doesNotMatch(a.html(),/case-graph-canvas/);
  a.go('Case graph');
  const graph=vm.runInContext('caseGraphPage.model',a.ctx);
  const edges=[...graph.edges.values()], docs=[...graph.nodes.values()].filter(n=>n.kind==='evidence');
  const edge=(from,to,role)=>edges.find(e=>e.source===from && e.target===to && e.role===role);
  assert.equal(docs.length,1);assert.deepEqual([...docs[0].sourceIds],[first.source_id,copy.source_id]);
  assert.equal(graph.nodes.has('finding:F1'),false);
  assert.equal(edge(graph.goal,'question:Q1','plan').citations.size,0);
  assert.ok(edge('question:Q1','question:Q2','plan'));
  assert.deepEqual([...edge('question:Q1',docs[0].id,'support').citations],['E1']);
  assert.deepEqual([...edge('question:Q1',docs[0].id,'contrary').citations],['E2']);
  assert.deepEqual([...edge(docs[0].id,'mailbox:sender@example.test','person').citations],['E1']);
  assert.equal(edge('question:Q1','hypothesis:Q1:0','plan').citations.size,0);
  assert.equal(vm.runInContext('caseGraphPage.slice.nodes.some(n=>n.kind==="hypothesis")',a.ctx),false);
  vm.runInContext('state.mapHypotheses=true;render();state.mapSelection="hypothesis:Q1:0";render()',a.ctx);
  assert.match(a.element('case-graph-detail').innerHTML,/Working hypothesis/);
  assert.doesNotMatch(a.element('case-graph-detail').innerHTML,/Source passages/);
  vm.runInContext('state.supportingOnly=true;render()',a.ctx);
  assert.equal(vm.runInContext('caseGraphPage.slice.edges.some(e=>e.role==="contrary")',a.ctx),false);
  vm.runInContext('state.sourceIds=["case:other.eml"];render()',a.ctx);
  assert.equal(vm.runInContext('caseGraphPage.model.nodes.size',a.ctx),1);
});

test('Case graph search includes late records and keeps every displayed result connected to the goal',()=>{
  const w=fixture();
  w.issues=Array.from({length:50},(_,i)=>{
    const s={...w.sources[0],source_id:'s'+i,relative_path:'Exhibit '+i,content_sha256:'v'+i};
    w.sources.push(s);
    w.evidence.push({...w.evidence[0],source_id:s.source_id,evidence_id:'p'+i,content_sha256:s.content_sha256});
    return {id:'q'+i,question:'Review document '+i,supporting_evidence:['p'+i],contradictory_evidence:[]};
  });
  const a=app(w);a.go('Case graph');
  const visible=()=>vm.runInContext('caseGraphPage.slice',a.ctx);
  assert.equal(visible().nodes.length,32);
  assert.ok(visible().nodes.some(n=>n.kind==='evidence'));
  vm.runInContext('state.mapQuery="Exhibit 49";render()',a.ctx);
  assert.equal(visible().nodes.length,3);assert.equal(visible().edges.length,2);
  assert.ok(visible().nodes.some(n=>n.label==='Exhibit 49'));
  vm.runInContext('state.mapQuery="Exhibit";render()',a.ctx);
  for(const n of visible().nodes)if(n.kind!=='goal')assert.ok(visible().edges.some(edge=>edge.target===n.id));
  vm.runInContext('state.mapQuery="missing item";render()',a.ctx);assert.equal(visible().nodes.length,0);
});

test('Old graph bookmarks open the case page and recipient briefings omit it',()=>{
  const w=fixture();w.saved_state={view:'People & relationships',graphMode:'case'};
  assert.equal(app(w).shell.view,'Case graph');
  w.package_mode='approved_excerpt_briefing';
  const a=app(w);a.go('Case graph');
  assert.equal(a.shell.view,'Overview');assert.equal(a.shell.config.tabs.some(t=>t[0]==='Case graph'),false);
  assert.doesNotMatch(a.html(),/Explore case graph/);
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

test('Incomplete review exposes exact assessment coverage and useful zero-finding actions',async()=>{
  const w=fixture();w.findings=[];
  w.analysis={status:'Incomplete analysis',stop_reason:'maximum_rounds_reached',scope:'Frozen sources'};
  w.coverage.assessor_source_ids=[];
  w.coverage.reviewer_source_ids=['case:notice.eml','hidden-source'];
  w.coverage.unreadable_ids=[];
  const a=app(w);
  assert.match(a.html(),/Review progress and next steps/);
  assert.match(a.html(),/configured investigation rounds were used/);
  assert.match(a.html(),/No draft findings were retained/);
  assert.match(a.html(),/does not establish that no relevant events occurred/);
  assert.match(a.html(),/aria-label="Sent for assessment: 0 of 1"/);
  assert.match(a.html(),/aria-label="Sent for independent review: 1 of 1"/);
  assert.match(a.html(),/>Search evidence</);
  await a.search('not a match');
  await a.click('coverage','reviewer_source_ids');vm.runInContext('render()',a.ctx);
  assert.equal(vm.runInContext('state.query',a.ctx),'');
  assert.match(a.html(),/notice.eml/);
  assert.equal(vm.runInContext('state.sourceIds.join(",")',a.ctx),'case:notice.eml');
  await a.click('coverage','assessor_source_ids');vm.runInContext('render()',a.ctx);
  assert.match(a.html(),/No documents match/);
});

test('Unresolved references remain in disclosure without looking like findings or source citations',()=>{
  const w=fixture();w.findings=[];
  const question='Examine job:'+'a'.repeat(64)+' before concluding.';
  w.supervision={next_review:{kind:'gap',gap_id:'G1',question,reason:'Resolve the enquiry.',timing:'Before further work',evidence_ids:[]},boundary:'No automatic action.'};
  const a=app(w);
  assert.match(a.html(),/<h3>Examine unresolved source reference before concluding\.<\/h3>/);
  assert.match(a.html(),/<details><summary>Original investigation question<\/summary><p>Examine job:/);
  assert.doesNotMatch(a.html(),/No matching retained passage/);
  assert.match(a.html(),/Not recorded/);
});
