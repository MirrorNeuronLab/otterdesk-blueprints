"""Layout invariants, bounded selection, deep graphs, and stable temporal scope."""
from pathlib import Path
import shutil
import subprocess

import pytest

ASSETS = Path(__file__).parents[2] / 'software_architecture_advisor/payloads/domain/workspace_assets'


def check(script):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for graph layout validation')
    subprocess.run([node, '-e', 'const model=require(process.argv[1]); const assert=require("node:assert/strict");'+script,
                    str(ASSETS/'graph-layout.js'), str(ASSETS/'graph-evolution.js')],
                   check=True, capture_output=True, text=True, timeout=15)


def test_cycles_remain_distinct_nodes_and_dag_edges_advance_toward_dependencies():
    check('''
const input={ids:['caller','a','b','dependency','isolated'],edges:[
 {source:'caller',target:'a'}, {source:'a',target:'b'}, {source:'b',target:'a'},
 {source:'b',target:'dependency'}, {source:'isolated',target:'isolated'}]};
const before=JSON.stringify(input), result=model.layout({...input,algorithm:"sequential"}), byId=new Map(result.nodes.map(n=>[n.id,n]));
assert.equal(JSON.stringify(input),before);assert.equal(result.nodes.length,5);
assert.equal(result.components,2);assert.equal(result.cycles,2);
assert.equal(byId.get('a').cycleGroup,byId.get('b').cycleGroup);
assert.equal(byId.get('caller').cycle,false);assert.equal(byId.get('isolated').cycle,true);
assert.ok(byId.get('caller').x<byId.get('a').x);assert.ok(byId.get('b').x<byId.get('dependency').x);
assert.equal(new Set(result.nodes.map(n=>n.x+':'+n.y)).size,5);
for(const n of result.nodes){assert.ok(n.x>=0 && n.x<=result.width);assert.ok(n.y>=0 && n.y<=result.height);}
assert.deepEqual(model.layout({ids:[...input.ids].reverse(),edges:[...input.edges].reverse(),algorithm:"sequential"}),result);
assert.deepEqual(model.layout({ids:[],edges:[]}).nodes,[]);
''')


def test_large_deep_chains_and_dense_cycles_do_not_overflow_stack_or_lose_nodes():
    check('''
const ids=Array.from({length:10000},(_,i)=>'node-'+String(i).padStart(5,'0'));
const edges=ids.slice(1).map((id,i)=>({source:ids[i],target:id}));
let result=model.layout({ids,edges,algorithm:"sequential"});assert.equal(result.nodes.length,10000);assert.equal(result.cycles,0);
for(let i=1;i<result.nodes.length;i++)assert.ok(result.nodes[i].x>result.nodes[i-1].x);
edges.push({source:ids.at(-1),target:ids[0]});result=model.layout({ids,edges,algorithm:"sequential"});
assert.equal(result.nodes.length,10000);assert.equal(result.cycles,1);
assert.equal(new Set(result.nodes.map(n=>n.x+':'+n.y)).size,10000);
assert.ok(result.nodes.every(n=>Number.isFinite(n.x+n.y)));
''')


def test_display_bounds_preserve_focus_and_explicitly_count_missing_relationships():
    check('''
const ids=['a','b','c','d','isolate'];const edges=[
 {source:'a',target:'b',kind:'call'}, {source:'a',target:'b',kind:'include'},
 {source:'b',target:'c',kind:'call'}, {source:'c',target:'d',kind:'call'},
 {source:'d',target:'external',kind:'call'}];
let plan=model.select({ids,edges,scope:'all',focus:'isolate',maxNodes:3,maxEdges:1});
assert.ok(plan.ids.includes('isolate'));assert.equal(plan.ids.length,3);assert.equal(plan.omittedNodes,2);
assert.equal(plan.scopeEdges,4);assert.equal(plan.edges.length,1);assert.equal(plan.omittedEdges,3);assert.equal(plan.invalidEdges,1);
plan=model.select({ids,edges,scope:'neighbors',focus:'a'});
assert.deepEqual(plan.ids,['a','b','c']);assert.equal(plan.edges.length,3);assert.equal(plan.hiddenNodes,2);
plan=model.select({ids,edges,scope:'connected',focus:'a'});
assert.equal(plan.ids.length,4);assert.equal(plan.hiddenNodes,1);
const withOtherFocus=model.select({ids,edges,scope:'connected',focus:'b'});
assert.deepEqual(plan.edges,withOtherFocus.edges); // selection alone does not relayout a bounded full graph
assert.equal(model.select({ids,edges,focus:'isolate'}).ids.length,5);
''')


def test_temporal_layout_uses_the_same_union_when_selected_state_changes():
    check('''
const fs=require('node:fs'),vm=require('node:vm'),calls=[];
const graphs=[{nodes:new Map([['a',{}],['b',{}]]),edges:[{source:'a',target:'b'}]},
 {nodes:new Map([['b',{}],['c',{}]]),edges:[{source:'b',target:'c'}]}];
const context={window:{ArchitectureNetwork:{render:c=>calls.push(c)}},document:{getElementById:()=>({value:'all'})}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const ctx={level:'file',frames:[{},{}],state:i=>i,entityGraph:i=>graphs[i],edgeKey:e=>e.source+'>'+e.target};
context.window.renderGraphEvolution({...ctx,graph:graphs[0]});
context.window.renderGraphEvolution({...ctx,graph:graphs[1]});
assert.equal(calls[0].layoutGraph,calls[1].layoutGraph);
assert.deepEqual([...calls[0].layoutGraph.nodes.keys()],['a','b','c']);
assert.equal(calls[0].layoutGraph.edges.length,2);assert.equal(calls[0].identity,'timeline');
''')


def test_worker_returns_errors_without_inventing_a_partial_layout():
    check('''
const fs=require('node:fs'),vm=require('node:vm'),replies=[];
const context={self:{postMessage:r=>replies.push(r)}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
context.self.onmessage({data:{id:1,graph:{ids:['a','b'],edges:[{source:'a',target:'b'}],algorithm:'sequential'}}});
assert.equal(replies[0].id,1);assert.equal(replies[0].result.nodes.length,2);
context.self.onmessage({data:{id:2,graph:{ids:null,edges:[]}}});
assert.equal(replies[1].id,2);assert.ok(replies[1].error);assert.equal(replies[1].result,undefined);
''')


def test_layout_choices_preserve_entities_edges_and_reproducible_coordinates():
    check('''
const ids=Array.from({length:550},(_,i)=>'f'+String(i).padStart(3,'0'));
const edges=ids.map((id,i)=>({source:id,target:ids[(i+1)%ids.length]}));
const before=JSON.stringify({ids,edges});
const defaultLayout=model.layout({ids,edges,focus:ids[0]});
assert.deepEqual(defaultLayout,model.layout({ids,edges,focus:ids[0],algorithm:'organic'}));
for(const algorithm of ['organic','sequential','radial']){
 const one=model.layout({ids,edges,focus:ids[0],algorithm});
 const two=model.layout({ids:[...ids].reverse(),edges:[...edges].reverse(),focus:ids[0],algorithm});
 assert.equal(one.nodes.length,550);assert.equal(one.cycles,1);
 assert.deepEqual(one,two);assert.ok(one.nodes.every(n=>Number.isFinite(n.x+n.y)));
}
assert.equal(JSON.stringify({ids,edges}),before);
assert.throws(()=>model.layout({ids,edges,algorithm:'unknown'}),/Unknown/);
''')


def test_radial_levels_are_minimum_undirected_distances_from_the_selection():
    check('''
const ids=['a','b','c','d','isolated'];
const edges=[{source:'a',target:'b'},{source:'b',target:'c'},{source:'d',target:'b'}];
const result=model.layout({ids,edges,algorithm:'radial',focus:'c'});
const byId=new Map(result.nodes.map(n=>[n.id,n]));
assert.equal(byId.get('c').distance,0);assert.equal(byId.get('b').distance,1);
assert.equal(byId.get('a').distance,2);assert.equal(byId.get('d').distance,2);
assert.equal(byId.get('isolated').distance,0);
const a=byId.get('a'),d=byId.get('d'),root=byId.get('c');
assert.ok(Math.abs(Math.hypot(a.x-root.x,a.y-root.y)-Math.hypot(d.x-root.x,d.y-root.y))<1e-9);
''')
