"""Architecture product projection of reusable static source/history facts."""
from pathlib import Path
import re
from collections import Counter

from mn_sdk.step_runtime import artifact_reference
from mn_static_code_analysis_skill import analyze_sources, analyze_history
from mn_static_code_analysis_skill.history import HistoryLimitError
from .catalog_contract import load_snapshot
from .catalog_store import CatalogStore
from .review_prompts import evidence_record

ARTIFACTS = [('static_code', 'data/static-code.json'),
             ('function_evolution', 'data/function-evolution.json'),
             ('code_map', 'web/code-map.html'), ('code_map_brief', 'reports/code-map.md'),
             ('architecture_score', 'data/architecture-score.json'), ('architecture_score_brief','reports/architecture-score.md')]


def build(block, snapshot=None):
    snapshot = snapshot or load_snapshot(block.store.run_dir)
    store = CatalogStore(block.store.run_dir)
    cfg = block.original_config['ingest']
    facts = analyze_sources({p: s['text'] for p,s in snapshot['sources'].items()},
        max_files=cfg['max_files'], max_file_bytes=cfg['max_file_bytes'], max_total_bytes=cfg['max_total_bytes'])
    facts['snapshot_id'] = snapshot['snapshot_id']
    manifest = snapshot['manifest']
    settings = block.original_config.get('analysis', {})
    repository = manifest.get('repository')
    if repository:
        try:
            history = analyze_history(repository, snapshot['inventory'], revision=manifest.get('git_anchor'),
                max_commits=min(settings.get('history_commits', 80), cfg['git_commits']),
                timeout_seconds=settings.get('history_timeout_seconds', 30), max_file_bytes=cfg['max_file_bytes'],
                include_historical_paths=True, exclude_parts=cfg.get('exclude', []))
        except HistoryLimitError as exc:
            # Current source facts remain useful when optional history exceeds
            # its explicit bounds. Never retry with a silently shortened window.
            history = unavailable_history(str(exc), settings)
    else:
        history = unavailable_history('Captured input has no local Git repository', settings)
    history['snapshot_id'] = snapshot['snapshot_id']
    store.write('data/static-code.json', facts)
    store.write('data/function-evolution.json', history)
    from .architecture_score import assess, markdown
    score = assess(facts, history)
    store.write('data/architecture-score.json', score)
    score_path = store.path('reports/architecture-score.md')
    score_text = markdown(score)
    if score_path.exists() and score_path.read_text() != score_text:
        raise ValueError('Architecture score changed on replay')
    score_path.parent.mkdir(parents=True, exist_ok=True)
    score_path.write_text(score_text)
    from .code_map import publish_shell, brief
    publish_shell(store.root)
    path = store.path('reports/code-map.md')
    text = brief(facts, history)
    if path.exists() and path.read_text() != text:
        raise ValueError('Static analysis changed on replay')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return [artifact_reference(name, path) for name,path in ARTIFACTS]


def unavailable_history(reason, settings):
    return {'schema_version': 'mn.function_evolution.v1', 'status': 'unavailable',
            'reason': reason, 'events': [], 'hotspots': [], 'cochange': [], 'version_edges': [],
            'coverage': {'model_calls': 0, 'requested_settings': settings},
            'limitations': ['Current static facts remain available; historical growth is unknown.',
                            'Reduce analysis.history_commits for fact/blob/byte limits; increase analysis.history_timeout_seconds only for a deadline limit.']}


def source_context(store, snapshot, task, focus):
    """Select actual whole functions plus their direct callees for model meaning.

    Candidate rows and complete definitions pass the existing atomic support
    admission with every other graph witness. Historical events stay in their
    own artifact; they cannot become current-source S- citations.
    """
    path = store.path('data/static-code.json')
    if not path.exists():
        return None, []
    facts = store.read('data/static-code.json')
    if facts['snapshot_id'] != snapshot['snapshot_id']:
        raise ValueError('Static analysis snapshot changed')
    history = store.read('data/function-evolution.json')
    if history['snapshot_id'] != snapshot['snapshot_id']:
        raise ValueError('Function history snapshot changed')
    functions = {f['id']:f for f in facts['functions'] if not f['ambiguous']
                 and f['evidence']['end_byte']-f['evidence']['start_byte'] <= 4000}
    changed = {f['function']:f['changes'] for f in history['hotspots']}
    degrees = {f['function']:f['call_sites_in'] for f in facts['hotspots']}
    linked = Counter()
    for call in facts['calls']:
        if call['target'] and call['path'] != call['target'].split('::',1)[0]:
            linked.update([call['source'],call['target']])
    terms = set(re.findall(r'[a-z]{3,}', focus.lower()))
    historical = task.get('aspect_id','').startswith('AR-14') or 'churn' in focus.lower() or 'co-change' in focus.lower()
    structural = task.get('aspect_id','').startswith(('AR-02','AR-04','AR-05','AR-14'))
    local_focus = focus.split(task.get('kind') or '\x00',1)[0]
    test_focus = bool(re.search(r'\b(tests?|testing|coverage|assert\w*)\b',local_focus.lower()))
    def test_path(path):
        p=Path(path)
        return bool({'test','tests'} & set(p.parts) or p.name.startswith('test_') or '.test.' in p.name or '.spec.' in p.name)
    ranking = sorted(functions, key=lambda key: (
        int(test_path(functions[key]['path']) != test_focus and task.get('path') != functions[key]['path']),
        -int(functions[key]['path'] in focus),
        -(changed.get(key,0) if historical else linked[key] if structural else 0),
        -len(terms & set(re.findall(r'[a-z]{3,}',key.lower()))),
        -(changed.get(key,0) if historical else degrees.get(key,0)), -degrees.get(key,0), key))
    rows, evidence = [], {}

    def witness(fn):
        loc = fn['evidence']
        body = snapshot['sources'][loc['path']]
        if body['sha256'] != loc['sha256']:
            raise ValueError('Static source witness changed')
        data = body['text'].encode()
        a,b = loc['start_byte'],loc['end_byte']
        text = data[a:b].decode()
        packet = {'path':loc['path'], 'sha256':loc['sha256'], 'text':text,
                  'start_offset':len(data[:a].decode()), 'end_offset':len(data[:b].decode()),
                  'start_line':loc['line_start'], 'end_line':loc['line_end']}
        record = evidence_record(packet)
        evidence[record['id']] = record
        return record['id']

    # Small overlapping candidates, never source-file-by-source-file model scans.
    selected, paths = [], set()
    for key in ranking:
        if functions[key]['path'] not in paths:
            selected.append(key)
            paths.add(functions[key]['path'])
        if len(selected) == 4:
            break
    selected += [key for key in ranking if key not in selected][:4-len(selected)]
    for key in selected:
        fn = functions[key]
        calls = [c for c in facts['calls'] if c['source']==key and c['target'] in functions]
        ids = [witness(fn)]
        targets = list(dict.fromkeys(c['target'] for c in calls))[:3]
        ids += [witness(functions[target]) for target in targets]
        rows.append({'function':key, 'candidate_callees':targets,
                     'other_resolved_call_sites':len(calls)-sum(c['target'] in targets for c in calls),
                     'source_evidence_ids':list(dict.fromkeys(ids)), 'support_complete':True,
                     'basis':'syntax/name candidates, not executed calls'})
    return {'tool':'static_function_neighborhood', 'status':'ok', 'rows':rows,
            'omitted_large_or_ambiguous_definitions':len(facts['functions'])-len(functions),
            'limit_note':'Up to four ranked functions, with distinct files preferred, and three direct callee definitions each. Architecture scope favors connected application functions unless tests or an exact path are requested; full graphs remain in data/static-code.json.'}, list(evidence.values())
