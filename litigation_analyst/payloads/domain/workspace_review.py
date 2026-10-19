"""Source-bound counsel reading view; no new inference, approvals or source acquisition."""
import hashlib
from types import SimpleNamespace

from .financial_review import build as reconcile


def verify(workspace):
    sources = {s['source_id']: s for s in workspace['sources']}
    evidence = {p['evidence_id']: p for p in workspace['evidence']}
    for source in sources.values():
        if source['text'] is not None and hashlib.sha256(source['text'].encode()).hexdigest() != source['content_sha256']:
            raise ValueError('Reading view source hash mismatch')
    for passage in evidence.values():
        source = sources.get(passage['source_id'])
        a, b = passage['start_offset'], passage['end_offset']
        if (source is None or source['text'] is None or passage['content_sha256'] != source['content_sha256']
                or not 0 <= a < b <= len(source['text']) or source['text'][a:b] != passage['text']):
            raise ValueError('Reading view citation mismatch')
    for event in workspace.get('financial_review', {}).get('events', []):
        if not event['evidence_ids'] or any(i not in evidence or evidence[i]['source_id'] != event['source_id']
                or evidence[i]['text'] != event['quote'] for i in event['evidence_ids']):
            raise ValueError('Reading view financial basis mismatch')
    fields = ('source_id', 'quote', 'event_type', 'amount', 'currency', 'transaction_ref', 'ledger_id', 'record_id', 'event_date')
    financial = reconcile({'financial_events': [{k: r[k] for k in fields if k in r}
        for r in workspace.get('financial_review', {}).get('events', [])]},
        [SimpleNamespace(**s) for s in sources.values()], {})
    return financial


def case_map(workspace):
    """Address identities, represented communications and annotated transaction records.

    A shared-source link is navigation, never an inferred participation or payment.
    Event nodes are source records; duplicate messages retain their occurrence IDs.
    """
    nodes, edges = {}, []
    events = workspace['temporal']['events'][:60]
    temporal_nodes = {n['id']: n for n in workspace['temporal']['nodes']}
    for event in events:
        refs = [p['evidence_id'] for p in event['evidence_refs']]
        nodes[event['id']] = {'id': event['id'], 'label': event['title'], 'kind': 'communication',
            'date': event['time']['earliest'], 'date_label': event['display'], 'evidence_ids': refs,
            'qualification': event['qualification'], 'source_ids': event['source_ids'],
            'occurrence_id': event.get('metric_occurrence_id')}
        for field, addresses in event['fields']['headers'].items():
            for address in addresses[:20]:
                original = temporal_nodes[address]
                nodes.setdefault(address, {'id': address, 'label': ' / '.join(original['names']) or address,
                    'detail': address, 'kind': 'correspondent', 'evidence_ids': [], 'source_ids': [],
                    'qualification': 'Name recorded in email headers. Address-level identity; person mapping is unverified.'})
                nodes[address]['evidence_ids'] = list(dict.fromkeys(nodes[address]['evidence_ids'] + refs))
                nodes[address]['source_ids'] = list(dict.fromkeys(nodes[address]['source_ids'] + event['source_ids']))
                edges.append({'source': address if field == 'From' else event['id'],
                    'target': event['id'] if field == 'From' else address,
                    'label': 'From header' if field == 'From' else field + ' header', 'evidence_ids': refs})
    records = workspace.get('financial_review', {}).get('events', [])[:60]
    for record in records:
        key = 'record:' + hashlib.sha256('|'.join(str(record[k]) for k in
            ('transaction_ref', 'currency', 'ledger_id', 'record_id')).encode()).hexdigest()[:20]
        transaction = 'transaction:' + record['transaction_ref']
        nodes.setdefault(transaction, {'id': transaction, 'label': record['transaction_ref'], 'kind': 'transaction',
            'evidence_ids': [], 'source_ids': [], 'qualification': 'Shared recorded reference; not proof of external payment or settlement.'})
        nodes[transaction]['evidence_ids'] = list(dict.fromkeys(nodes[transaction]['evidence_ids'] + record['evidence_ids']))
        nodes[transaction]['source_ids'] = list(dict.fromkeys(nodes[transaction]['source_ids'] + [record['source_id']]))
        nodes[key] = {'id': key, 'label': record['event_type'].replace('_', ' ').capitalize() + ' · ' + record['currency'] + ' ' + record['amount'],
            'kind': 'financial_record', 'date': record.get('event_date'), 'date_label': record['date_basis'],
            'evidence_ids': record['evidence_ids'], 'source_ids': [record['source_id']],
            'qualification': record['classification_basis']}
        edges.append({'source': key, 'target': transaction, 'label': 'Recorded reference', 'evidence_ids': record['evidence_ids']})
        for event in events:
            if record['source_id'] in event['source_ids']:
                edges.append({'source': event['id'], 'target': key, 'label': 'Same source',
                    'evidence_ids': list(dict.fromkeys(record['evidence_ids'] + [p['evidence_id'] for p in event['evidence_refs']]))})
    return {'nodes': list(nodes.values()), 'edges': edges,
        'omitted_communications': max(0, len(workspace['temporal']['events']) - len(events)),
        'omitted_financial_records': max(0, len(workspace.get('financial_review', {}).get('events', [])) - len(records)),
        'definition': 'Named correspondents → communication records → annotated financial records → transaction references. Links do not establish causation, receipt, identity or liability.'}


def attach(workspace):
    from .review_packets import consistency_checks

    # Recompute totals from verified annotated quotations rather than cached totals.
    workspace['financial_review'] = verify(workspace)
    checks = consistency_checks({'findings': workspace['findings']}, workspace['financial_review'])
    evidence_ids = {p['evidence_id'] for p in workspace['evidence']}
    checks += [c for c in workspace.get('consistency', {}).get('checks', [])
        if set(c.get('evidence_ids', [])) <= evidence_ids and c not in checks]
    blocked = {c['finding_id'] for c in checks}
    workspace['reading_review'] = {'checks': checks, 'withheld_finding_ids': sorted(blocked),
        'definition': 'Limited checks for explicit absence claims and annotated ledger conflicts. Passing is not a substantive accuracy determination.'}
    workspace['reading_tasks'] = review_tasks(workspace)
    workspace['case_map'] = case_map(workspace)
    workspace['reading_reports'] = reports(workspace)
    return workspace


def md(value):
    return str(value or '').replace('\\', '\\\\').replace('|', '\\|').replace('\n', ' ')


def review_tasks(workspace):
    tasks = []
    financial = workspace['financial_review']
    for t in financial['transactions']:
        records = [r for r in financial['events'] if all(r[k] == t[k] for k in ('transaction_ref', 'currency', 'ledger_id'))]
        approved = [r for r in records if r['event_type'] == 'approved']
        postings = [r for r in records if r['event_type'] in {'posting', 'reversal', 'net_balance'}]
        if approved:
            tasks.append({'title': 'Confirm the scope of written approval', 'status': 'Internal reread',
                'record': 'The request and stated approval for ' + t['transaction_ref'],
                'purpose': 'Distinguish the amount requested from the amount approved. Read conditions and any exception requirements in context.',
                'closure': 'Record the authorized amount, any conditions and the source basis for any larger approval.',
                'evidence_ids': [i for r in records if r['event_type'] in {'requested', 'approved'} for i in r['evidence_ids']]})
        if postings:
            tasks.append({'title': 'Reconcile the posting and reversal', 'status': 'Internal reread',
                'record': 'Ledger records for ' + t['transaction_ref'],
                'purpose': 'Test any loss statement against the supplied posting, reversal and recorded net. Keep accounting and external settlement separate.',
                'closure': 'Tie the selected ledger entries and net to their original records and explain any discrepancy.',
                'evidence_ids': [i for r in postings for i in r['evidence_ids']]})
        if not any(r['event_type'] == 'settlement' for r in records):
            tasks.append({'title': 'Resolve external bank settlement', 'status': 'Evidence check',
                'record': 'Bank statements, confirmation or settlement records for ' + t['transaction_ref'],
                'purpose': 'No source-bound settlement annotation was supplied. Inspect the full materials before deciding which bank-side records counsel should request.',
                'closure': 'Source-backed reconciliation of external settlement with the ledger, or a documented remaining limitation.',
                'evidence_ids': t['evidence_ids']})
    for i, task in enumerate(tasks):
        task.update(id='reading-task-' + str(i), owner='Unassigned', origin='Proposed internal review; no collection or contact performed')
    return tasks


def citations(ids):
    return ' '.join(f'[Source {n + 1}](exact-source-passages.md#{i})' for n, i in enumerate(dict.fromkeys(ids)))


def reports(workspace):
    blocked = set(workspace['reading_review']['withheld_finding_ids'])
    financial = workspace['financial_review']
    lines = ['# Counsel review brief', '', '**Draft for attorney review.** Source statements and annotations are not legal conclusions.', '',
        '## Decision to support', '', md(workspace.get('matter_scope', {}).get('intended_decision') or workspace['goal']), '',
        '## What the transaction records show', '',
        '| Reference | Recorded event | Amount | Basis |', '| --- | --- | ---: | --- |']
    for record in financial['events']:
        lines.append('| ' + ' | '.join([md(record['transaction_ref']), md(record['event_type'].replace('_', ' ')),
            md(record['currency'] + ' ' + record['amount']), citations(record['evidence_ids'])]) + ' |')
    if not financial['events']:
        lines += ['', 'No counsel-labelled transaction records supplied. Inspect the source records; absence of annotations does not establish absence of evidence.']
    for t in financial['transactions']:
        lines += ['', '### ' + md(t['transaction_ref']), '',
            '- Request less stated approval: ' + md(t['currency']) + ' ' + md(t['request_minus_approval'] or 'Not established') + '.',
            '- Posting / reversal net: ' + md(t['currency']) + ' ' + md(t['posting_reversal_net'] or 'Not established') + '.',
            '- Recorded net values: ' + md(', '.join(t['recorded_net_values']) or 'Not supplied') + '.', '',
            citations(t['evidence_ids']), '', md(t['qualification'])]
    if workspace.get('counsel_issues'):
        lines += ['', '## Counsel questions', '', 'Counsel-supplied review direction; applicable law is not verified.', '']
        for issue in workspace['counsel_issues']:
            retained = [f for f in workspace['findings'] if f['id'] not in blocked and issue['id'] in f.get('counsel_issue_ids', [])]
            lines += ['### ' + md(issue['question']), '',
                md(' '.join(f['assessment'] for f in retained) or 'No retained narrative answer is established. Review the transaction records and reconcile any conflicting AI draft before using a proposed answer.'), '',
                citations([i for f in retained for i in f['supporting_evidence']]), '']
    lines += ['', '## Draft claims requiring correction', '']
    for f in workspace['findings']:
        if f['id'] in blocked:
            ids = [i for c in workspace['reading_review']['checks'] if c['finding_id'] == f['id'] for i in c['evidence_ids']]
            lines += ['### ' + md(f['title']), '', 'Withheld from the reading brief and reviewed briefing. An available transaction record conflicts with an absence claim. Reconcile the complete source before relying on this wording.', '', citations(ids), '']
    if not blocked:
        lines += ['No conflict was detected by the limited deterministic checks. Substantive attorney review remains outstanding.', '']
    lines += ['## Retained draft findings', '']
    for f in workspace['findings']:
        if f['id'] not in blocked:
            lines += ['### ' + md(f['title']), '', md(f['assessment']), '', citations(f['supporting_evidence']), '',
                '**Contrary records:** ' + citations(f['counter_evidence']), '', '**Limitations:** ' + md(f['limitations']), '']
    if not any(f['id'] not in blocked for f in workspace['findings']):
        lines += ['No narrative finding is retained in this reading brief. The source-bound transaction records above remain available for review.', '']
    lines += ['## Next review work', '']
    for task in workspace['reading_tasks']:
        lines += ['### ' + md(task['title']), '', '- Route: ' + md(task['status']),
            '- Record: ' + md(task['record']), '- Decision it informs: ' + md(task['purpose']),
            '- Closure test: ' + md(task['closure']), '- Owner: Unassigned', '', citations(task['evidence_ids']), '']
    for gap in ([] if workspace['reading_tasks'] else workspace['gaps']):
        lines += ['### ' + md(gap['question']), '',
            '- Route: ' + md(gap.get('status', 'Needs review')) + '.',
            '- Record or interview: ' + md(gap.get('requested_record', gap['question'])) + '.',
            '- Decision it informs: ' + md(gap.get('why_it_matters', 'Clarify the factual question')) + '.',
            '- Closure test: ' + md(gap['closure_condition']) + '.',
            '- Owner: ' + md(gap.get('owner') or 'Unassigned') + '. Internal target: ' + md(gap.get('internal_target') or 'Not assigned') + '.', '',
            citations(gap['source_evidence_ids']), '']
    lines += ['No collection, contact or legal action was performed.', '', '## Scope and limits', '',
        md(workspace['analysis']['status']) + '. ' + md(workspace['analysis']['scope']), '',
        'Readable text, packet admission, model checking and attorney approval are separate. Original authenticity, applicable law, external settlement and legal liability remain unverified.']
    appendix = ['# Exact source passages', '', 'Generated normalized character locators. Verify originals and surrounding context.', '']
    for p in workspace['evidence']:
        appendix += ['## ' + p['evidence_id'], '', md(p['source_id']) + f" · characters {p['start_offset']}:{p['end_offset']}", '',
            *['> ' + line for line in p['text'].splitlines()], '', citations([p['evidence_id']]), '']
    return [{'id': 'counsel-brief', 'title': 'Counsel review brief', 'filename': 'counsel-review-brief.md', 'markdown': '\n'.join(lines)},
        {'id': 'source-passages', 'title': 'Exact source passages', 'filename': 'exact-source-passages.md', 'markdown': '\n'.join(appendix)}]
