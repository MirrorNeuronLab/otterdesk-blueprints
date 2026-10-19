"""Observable presentation decisions over saved graph evidence, without a browser."""
from pathlib import Path
import shutil
import subprocess

import pytest

MODEL = Path(__file__).parents[2] / 'software_architecture_advisor/payloads/domain/workspace_assets/overview-model.js'


def check(script):
    node = shutil.which('node')
    if node is None: pytest.skip('Node is required for the standalone browser policy checks')
    subprocess.run([node, '-e', 'const model=require(process.argv[1]);const assert=require("node:assert/strict");'+script,
                    str(MODEL)], check=True, capture_output=True, text=True, timeout=10)


def test_incomplete_recommendation_cannot_displace_measured_investigation():
    check('''
const facts={components:[{id:'a.c',fan_in:5,fan_out:2,status:'parsed'},
 {id:'b.c',fan_in:1,fan_out:1,status:'parsed'}],cycles:[['a.c','b.c']],
 calls:[{target:'b.c::run'},{target:null}],coverage:{status_counts:{parsed:2},unresolved_calls:1}};
const history={timeline:{frames:[{baseline:true,changed_paths:[],gaps:[],component_edges:[],calls:[],nodes:[]},
 {changed_paths:['b.c'],gaps:[],component_edges:[],calls:[],nodes:[]}]}};
const plan={mode:'Plan',record_type:'work_package',record_id:'p',finding_ids:[],omitted_source_records:0};
const report={findings:[],improvement_prompts:{prompts:[plan,
 {mode:'Investigate',record_type:'cycle',target_files:['a.c','b.c']}]}};
let view=model.project(facts,history,report);
assert.equal(view.planIndex,-1);assert.equal(view.lead.id,'b.c');assert.equal(view.changedCommits,1);
assert.equal(view.investigateIndex,1);assert.equal(view.linkedCalls,1);assert.equal(view.hasHistory,true);
report.findings=[{id:'f',status:'supported'}];plan.finding_ids=['f'];
report.improvement_prompts.prompts.push({...plan,mode:'Implement'});
assert.equal(model.project(facts,history,report).planIndex,0);
plan.omitted_source_records=1;
assert.equal(model.project(facts,history,report).planIndex,-1);
''')


def test_topology_shortlist_compares_relationships_and_ignores_parser_gap_removals():
    check('''
const a={id:'a.c::run',path:'a.c'}, b={id:'b.c::run',path:'b.c'}, c={id:'c.c::run',path:'c.c'};
const ab={source:a.id,target:b.id},bc={source:b.id,target:c.id};
const first={commit:'1',subject:'base',nodes:['a','b'],calls:['ab'],gaps:[],component_edges:[['a.c','b.c','call',1]]};
const second={...first,commit:'2',subject:'body edit only',nodes:['a2','b'],calls:['ab2']};
const third={...second,commit:'3',subject:'new relationship',nodes:['a2','b','c'],calls:['ab2','bc'],
 component_edges:[...first.component_edges,['b.c','c.c','call',1]]};
const fourth={...third,commit:'4',subject:'parser gap',nodes:['b','c'],calls:['bc'],gaps:['a.c'],
 component_edges:[['b.c','c.c','call',1]]};
const history={timeline:{definitions:{a,a2:{...a,body_sha256:'changed'},b,c},calls:{ab,ab2:ab,bc},
 frames:[first,second,third,fourth]}};
const rows=model.topologyChanges(history);
assert.equal(rows.length,1);assert.equal(rows[0].index,2);
assert.equal(rows[0].callsAdded,1);assert.equal(rows[0].filesAdded,1);assert.equal(rows[0].nodesAdded,1);
assert.equal(rows[0].callsRemoved,0);
assert.equal(rows[0].level,'function');assert.equal(rows[0].focus,'b.c::run');
''')


def test_unknown_formats_and_empty_graph_never_receive_a_fake_connected_lead():
    check('''
const facts={components:[{id:'src/main.dsl',fan_in:0,fan_out:0,status:'unsupported'},
 {id:'Dockerfile',fan_in:0,fan_out:0,status:'unsupported'}],cycles:[],calls:[],
 coverage:{status_counts:{unsupported:2},unresolved_calls:0}};
const view=model.project(facts,{},{});
assert.equal(view.lead,undefined);assert.equal(view.parsed,0);assert.equal(view.unsupported,2);
assert.equal(view.planIndex,-1);assert.deepEqual(view.topology,[]);assert.equal(view.hasHistory,false);
assert.deepEqual(view.unsupportedTypes,[['.dsl',1],['Dockerfile',1]]);
''')


def test_text_only_and_missing_history_never_become_zero_churn():
    check('''
const components=[{id:'src/core.c'},{id:'src/build.sh'}];
const frames=[{baseline:true,files:[['src/core.c','parsed',2]],nodes:['a'],gaps:[]},
 {baseline:false,files:[['src/core.c','partial',2]],nodes:[],gaps:['src/core.c']}];
const history={timeline:{definitions:{a:{id:'src/core.c::run'}}}};
assert.deepEqual(model.historyCoverage('src/build.sh','file',components,history,frames),{known:false,partial:true});
assert.deepEqual(model.historyCoverage('src/core.c','file',components,history,frames),{known:true,partial:false});
assert.deepEqual(model.historyCoverage('src/core.c::run','function',components,history,frames),{known:true,partial:true});
assert.deepEqual(model.historyCoverage('src/core.c','file',components,{},[]),{known:false,partial:false});
''')


def test_score_summary_preserves_partial_weight_instead_of_inventing_a_grade():
    check('''
const score={assessed_weight:70,score:null,range:{lower:58.12,upper:88.12},
 dimensions:[{id:'modularity',points:20.76},{id:'dependencies',points:19.18}]};
const summary=model.scoreSummary(score);
assert.equal(summary.value,'58.1–88.1 / 100');
assert.equal(summary.note,'Provisional range · 70/100 scoring points assessed');
assert.equal(score.score,null);
score.assessed_weight=100;score.score=0;score.range={lower:0,upper:0};
assert.deepEqual(model.scoreSummary(score),{value:'0 / 100',note:'Provisional · 100/100 scoring points assessed'});
''')


def test_score_summary_distinguishes_missing_unknown_and_history_only_evidence():
    check('''
assert.equal(model.scoreSummary(undefined).value,'Not available');
const score={assessed_weight:0,score:null,range:{lower:0,upper:100},
 dimensions:[{id:'dependencies',points:null}]};
assert.equal(model.scoreSummary(score).value,'Not assessed');
score.assessed_weight=20;score.range={lower:12.46,upper:92.46};
score.dimensions.push({id:'change_isolation',points:12.46});
assert.deepEqual(model.scoreSummary(score),{value:'Evidence incomplete',
 note:'20/100 scoring points assessed · Structural evidence missing'});
''')
