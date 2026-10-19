"""Adapt shared syntax facts to the advisor's existing evidence graph contract."""
from mn_static_code_analysis_skill import analyze_sources


def facts(sources):
    return analyze_sources({p: s['text'] for p,s in sources.items() if not p.endswith('.py')})


def symbols(records, project):
    paths = {info['path']: name for name,info in project.modules.items()}
    for fn in project.polyglot['functions']:
        if fn['path'] not in paths or fn['ambiguous']:
            continue
        module = paths[fn['path']]; loc = fn['evidence']
        eid = records.cite(fn['path'], loc['line_start'], loc['line_end'], detail='Tree-sitter function definition')
        key = records.node(project.key(module, fn['name']), 'Symbol', name=fn['name'].split('.')[-1],
            qualified_name=module+'.'+fn['name'], module=module, path=fn['path'],
            line=loc['line_start'], end_line=loc['line_end'], evidence_id=eid, category='FunctionDefinition')
        records.edge('module:'+module, key, 'DECLARES', eid)


def dependencies(records, project):
    paths = {info['path']: name for name,info in project.modules.items()}
    for edge in project.polyglot['component_evidence']:
        if edge['source'] not in paths or edge['target'] not in paths:
            continue
        loc = edge['evidence']
        eid = records.cite(loc['path'],loc['line_start'],loc['line_end'], detail=edge['kind']+' syntax candidate')
        records.edge('module:'+paths[edge['source']], 'module:'+paths[edge['target']], 'DEPENDS_ON', eid,
                     detail=edge['kind']+' candidate; build, preprocessing and runtime unverified')
    records.details['polyglot_coverage'] = project.polyglot['coverage']
    records.details['limitations'].extend(project.polyglot['limitations'])


def calls(records, project):
    paths = {info['path']: name for name,info in project.modules.items()}
    functions = {f['id']:f for f in project.polyglot['functions'] if not f['ambiguous'] and f['path'] in paths}
    for number, call in enumerate(project.polyglot['calls']):
        if call['source'] not in functions:
            continue
        fn = functions[call['source']]; module = paths[fn['path']]; loc = call['evidence']
        eid = records.cite(loc['path'],loc['line_start'],loc['line_end'],detail='call syntax/name candidate')
        if call['target'] in functions:
            target = functions[call['target']]
            records.edge(project.key(module,fn['name']),project.key(paths[target['path']],target['name']), 'CALLS', eid,
                         detail='syntax/name candidate; type, build and runtime unverified')
        else:
            key = records.node(f'callsite:{module}:static:{number}', 'CallSite', name=call['name'],
                               module=module,path=fn['path'],line=loc['line_start'],resolution=call['reason'])
            records.edge(project.key(module,fn['name']),key,'CALLS_UNRESOLVED',eid)
