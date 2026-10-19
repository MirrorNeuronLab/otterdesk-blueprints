"""Pure comparison presentation over immutable saved graph evidence."""
from pathlib import Path
import shutil
import subprocess
import pytest

ASSETS = Path(__file__).parents[2] / 'software_architecture_advisor/payloads/domain/workspace_assets'

def check(script):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for browser presentation validation')
    subprocess.run([node, '-e', 'const model=require(process.argv[1]);const assert=require("node:assert/strict");'+script,
                    str(ASSETS/'comparison-presentation.js'),str(ASSETS/'graph-layout.js')],
                   check=True,capture_output=True,text=True,timeout=15)

def test_baseline_modes_same_state_and_undated_window_start():
    check('''
const frames=[{commit:'a'.repeat(40),date:null,subject:'Window baseline'},
 {commit:'b'.repeat(40),date:'2020-01-01',subject:'First change'},
 {commit:'c'.repeat(40),date:'2019-01-01',subject:'Second change'}];
assert.equal(model.context(frames,2).mode,'Since window start');
assert.equal(model.context(frames,2).baseline.date,null);
assert.equal(model.context(frames,2,'previous').before,1);
assert.equal(model.context(frames,2,'previous').mode,'Since previous commit');
assert.equal(model.context(frames,2,'1').mode,'Custom comparison');
assert.equal(model.context(frames,0,'previous').same,true);
assert.equal(model.context(frames,2,'2').same,true);
assert.equal(model.context(frames,0).selected.label,'Window baseline');
''')

def test_topology_ranking_counts_and_definition_edits_are_separate():
    check('''
const node=(id,hash='one')=>[id,{id,functions:[{id,body_sha256:hash}]}];
const graph=(nodes,edges)=>({nodes:new Map(nodes),edges:edges.map(([source,target])=>({source,target,kind:'call'}))});
const old=graph([node('a'),node('b'),node('edit'),node('gone')],[['a','b'],['gone','b']]);
const graphNow=graph([node('a'),node('b'),node('edit','two'),node('new')],[['b','a'],['new','a']]);
const result=model.present({graph:graphNow,old});
assert.equal(result.added.size,2);assert.equal(result.removed.size,2);
assert.equal(result.entries.get('a').beforeOut,1);assert.equal(result.entries.get('a').afterIn,2);
assert.equal(result.entries.get('edit').definitionOnly,true);
assert.equal(result.entries.get('gone').status,'Removed');
assert.ok(result.entries.get('gone').before);assert.equal(result.entries.get('gone').after,null);
assert.deepEqual(result.highlights.map(r=>r.id),['a','b','gone']);
assert.match(model.describe(result.entries.get('edit')),/no observed topology change/);
assert.equal(model.present({graph:old,old}).highlights.length,0);
''')

def test_parser_gaps_suppress_false_removals_and_uncertain_cycle_changes():
    check('''
const nodes=new Map(['a','gap','b'].map(id=>[id,{id,functions:[]}]))
const old={nodes,edges:[{source:'a',target:'gap',kind:'call'},{source:'gap',target:'a',kind:'call'},{source:'a',target:'b',kind:'call'}]};
const graph={nodes:new Map([['a',nodes.get('a')],['b',nodes.get('b')]]),edges:[]};
const r=model.present({graph,old,gaps:['gap']});
assert.equal(r.entries.get('gap').status,'Comparison incomplete');
assert.equal(r.statuses.has('gap'),false);assert.equal(r.removed.size,1);
assert.equal(r.entries.get('a').cycleIncomplete,true);assert.equal(r.entries.get('a').cycleChanged,false);
assert.equal(r.incomplete,true);
const clean=model.present({graph,old});
assert.equal(clean.entries.get('a').cycleChanged,true);
assert.match(model.describe(clean.entries.get('a')),/yes → no/);
''')

def test_framing_uses_visible_positions_and_only_displayed_comparable_changes():
    check('''
const change={statuses:new Map([['edited','modified'],['hidden','removed']]),
 added:new Set(['a\\0b\\0call','a\\0hidden\\0call']),removed:new Set()};
assert.deepEqual([...model.changeIds(change,['a','b','edited'],[{source:'a',target:'b',kind:'call'}])].sort(),['a','b','edited']);
assert.deepEqual([...model.changeIds(change,['unrelated'],[])],[]);
change.entries=new Map([['cycle-only',{id:'cycle-only',cycleChanged:true}]]);
assert.deepEqual([...model.changeIds(change,['cycle-only'],[])],['cycle-only']);
assert.deepEqual(model.bounds([{x:100,y:200},{x:150,y:300}]),{x0:100,y0:200,x1:150,y1:300});
assert.equal(model.bounds([]),null);
assert.equal(model.bounds([{x:NaN,y:5}]),null);
''')

def test_scope_counts_separate_history_filters_caps_and_parser_gaps():
    check('''
const graph={nodes:new Map(['a','b','gap','isolated'].map(id=>[id,{}])),edges:[]};
const old={nodes:new Map([['removed',{}],['a',{}]]),edges:[]};
const plan={totalNodes:100,scopeIds:['a','b','gap','removed','historical-only'],ids:['a','gap','removed'],omittedEdges:7};
const r=model.coverage({graph,old,plan,change:{gaps:new Set(['gap'])},capturedFiles:20,comparisonFiles:6,level:'function'});
assert.deepEqual(r,{unit:'functions',capturedFiles:20,comparisonFiles:6,inventory:5,comparable:4,scopeEligible:4,displayed:3,
 hiddenByScope:1,hiddenByLimit:1,gapNodes:1,gapFiles:1,historicalInventory:100,relationshipLimit:7});
assert.equal(r.inventory,r.displayed+r.hiddenByScope+r.hiddenByLimit);
''')

def test_investigation_matches_function_source_and_preserves_canonical_prompt():
    check('''
const prompts=[{mode:'Plan',target_files:['src/a.c'],prompt:'plan'},
 {mode:'Investigate',target_files:['src/a.c'],prompt:'canonical\\ntext'}];
assert.equal(model.investigation(prompts,'src/a.c::foo').prompt.prompt,'canonical\\ntext');
assert.equal(model.investigation(prompts,'other.py'),null);
''')

def test_renderer_fits_visible_nodes_and_preserves_camera_across_replay():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for renderer validation')
    subprocess.run([node,str(Path(__file__).with_name('network_presentation_test.cjs')),str(ASSETS)],
                   check=True,capture_output=True,text=True,timeout=15)
