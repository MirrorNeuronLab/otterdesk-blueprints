"""Inspect a frozen EMC-2 run without inference or access to mutable originals."""
import argparse
import hashlib
import json
from pathlib import Path


def evaluate(root, expected):
    if expected.resolve().is_relative_to(root.resolve()):
        raise ValueError('Keep expected criteria outside the run and case inputs')
    inventory = json.loads((root / 'case/source_inventory.json').read_text())
    sources = json.loads((root / 'case/sources.json').read_text())
    if hashlib.sha256((root / 'case/sources.json').read_bytes()).hexdigest() != inventory['sources_sha256']:
        raise ValueError('Frozen source inventory hash mismatch')
    by_id = {d['source_id']:d for d in sources}
    labels = json.loads(expected.read_text())
    matches = []
    for label in labels['labels']:
        source = by_id.get(label['source_id'])
        valid = bool(source and source['text'] is not None and source['content_sha256']==label['source_sha256'] and
            source['text'][label['start_offset']:label['end_offset']]==label['quote'])
        matches.append({'id':label['id'], 'source_binding_valid':valid,
            'criterion':label['criterion'], 'semantic_retention':'pending_attorney_review'})
    workspace_path = root / 'case/workspace.json'
    workspace = json.loads(workspace_path.read_text()) if workspace_path.is_file() else {}
    invalid = []
    for evidence in workspace.get('evidence', []):
        source = by_id.get(evidence['source_id'])
        if not source or source['text'] is None or source['content_sha256'] != evidence['content_sha256'] or source['text'][evidence['start_offset']:evidence['end_offset']] != evidence['text']:
            invalid.append(evidence['evidence_id'])
    return {'revision':labels['revision'], 'sample_binding_matches':inventory.get('sample_attribution', {}).get('revision')==labels['revision'],
        'document_count':inventory['document_count'], 'readable_count':inventory['readable_count'],
        'unreadable_sources':inventory['unreadable_sources'], 'attachment_processing':inventory.get('attachment_processing', []),
        'archives_not_extracted':inventory.get('archives_not_extracted', []),
        'duplicate_group_count':len(inventory.get('duplicate_source_groups', [])),
        'excluded_repository_documentation':inventory.get('sample_attribution', {}).get('excluded_repository_documentation', []),
        'label_checks':matches, 'invalid_citation_ids':invalid,
        'citation_check_status':'checked' if workspace_path.is_file() else 'no_report_yet',
        'acceptance':'pending_attorney_review',
        'qualification':'Coverage and exact bindings do not measure narrative accuracy. No source code or attachments were executed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--expected', type=Path, default=Path(__file__).parent / 'examples/emc2_evaluation/expected.json')
    args = parser.parse_args()
    print(json.dumps(evaluate(args.run, args.expected), indent=2))
