"""Offline retrieval/admission audit of a delivered run; never a new conformance verdict.

Use authorized local captures only. Output contains rule text and source paths and
must remain confidential. No model, runtime, repository program or test executes.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payloads'))
from domain.document_policy import document_reason, line_contexts
from domain.retrieval import EvidenceWorkspace
from domain.source_policy import evidence_paths, source_role
from mn_static_code_analysis_skill import SUPPORTED_EXTENSIONS, analyze_sources


def audit(capture, report):
    sources = capture['sources']
    analysis = analyze_sources({p: text for p, text in sources.items() if Path(p).suffix in SUPPORTED_EXTENSIONS})
    workspace = EvidenceWorkspace(sources, analysis)
    if workspace.index.snapshot_id != report['snapshot_id'] or capture['snapshot_id'] != report['snapshot_id']:
        raise ValueError('Capture and report identities differ.')
    rules = {r['id']:r for r in report['rules']}
    resolved = [r for r in report['results'] if r['status'] != 'unknown']
    groups = defaultdict(list)
    for result in report['results']:
        if result['status'] == 'unknown':
            groups[rules[result['rule_id']]['source']['path']].append(result)
    selected_unknowns = []
    for position in range(max((len(g) for g in groups.values()), default=0)):
        for path in sorted(groups):
            if len(groups[path]) > position and len(selected_unknowns) < 26:
                selected_unknowns.append(groups[path][position])
    rows = []
    for original in resolved + selected_unknowns:
        rule = rules[original['rule_id']]
        origin = rule['source']
        reason = document_reason(origin['path'], 'current_requirements')
        contexts = line_contexts(sources[origin['path']])
        if not reason and not any(contexts.get(n, {}).get('eligible') for n in range(origin['start_line'], origin['end_line'] + 1)):
            reason = 'non_normative_example_or_instruction'
        candidates, seeded = workspace.seed(rule)
        eligible = set(evidence_paths(rule, sources))
        admitted = [e for e in original['evidence'] if e['path'] in eligible]
        original_reads = [s['request']['path'] for s in original.get('investigation', [])
                          if s.get('request', {}).get('action') == 'read']
        rows.append({'rule_id':rule['id'], 'statement':rule['statement'], 'original_status':original['status'],
            'origin':origin, 'extraction_exclusion':reason,
            'original_read_roles':dict(Counter(source_role(p) for p in original_reads)),
            'original_evidence_roles':dict(Counter(source_role(e['path']) for e in original['evidence'])),
            'evidence_admission':'ineligible_source' if original['status'] != 'unknown' and not admitted else 'requires_independent_review',
            'ranked_candidates':candidates['matches'],
            'seeded_reads':[{k:s[k] for k in ('path', 'start_line', 'end_line', 'sha256', 'definition_complete')} for s in seeded]})
    unknowns = [r for r in rows if r['original_status'] == 'unknown']
    return {'schema':'mn.code_verifier.offline_comparison.v1', 'snapshot_id':report['snapshot_id'],
        'qualification':'retrieval_and_evidence_policy_audit_only; not_new_pass_fail_judgments',
        'model_calls':0, 'source_execution':False,
        'summary':{'rows':len(rows), 'original_conclusive':len(resolved), 'sampled_unknowns':len(unknowns),
            'conclusive_with_ineligible_evidence':sum(r['original_status'] != 'unknown' and r['evidence_admission'] == 'ineligible_source' for r in rows),
            'excluded_requirement_sources':sum(bool(r['extraction_exclusion']) for r in rows),
            'unknowns_with_prior_production_reads':sum(r['original_read_roles'].get('production_source', 0) > 0 for r in unknowns),
            'unknowns_with_new_production_reads':sum(bool(r['seeded_reads']) for r in unknowns)}, 'rows':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.run.resolve(strict=True)
    output = args.output_dir.resolve()
    if output == source or source in output.parents:
        raise ValueError('Write comparisons outside the delivered run.')
    capture = json.loads((source / 'capture.json').read_text())
    report = json.loads((source / 'result.json').read_text())
    result = audit(capture, report)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Code verifier capture comparison', '',
        'Offline retrieval and evidence-policy audit. No new pass/fail judgments, model calls or source execution.', '',
        *[f'- {name}: {value}' for name, value in result['summary'].items()], '',
        '| Rule | Original | Source qualification | New source candidates |', '| --- | --- | --- | --- |']
    for row in result['rows']:
        candidates = ', '.join(f"{r['path']}:{r['start_line']}–{r['end_line']}" for r in row['seeded_reads']) or 'None'
        lines.append(f"| {row['rule_id']} | {row['original_status']} | {row['extraction_exclusion'] or row['evidence_admission']} | {candidates} |")
    (output / 'comparison.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
