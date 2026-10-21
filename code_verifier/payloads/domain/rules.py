"""Product policy: atomic software expectations and supervisor Markdown overrides."""
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from mn_code_search_skill import TextSearchIndex
from mn_sdk.agent_events import report_activity
from mn_sdk.llm import LLMError

from .artifacts import read, save, text
from .model import ask, client, failure_details
from .extraction_outcome import require_rule_candidates
from .publication import deliver_reports
from .configuration import BLUEPRINT_ID, settings
from .rule_sources import (ExtractionContractError, SourceSelectionError,
                           source_lines, bind_sources, apply_source_repairs)
from . import rule_cache
from .rule_document import short_title

HEADING = re.compile(r'^## ([A-Za-z][A-Za-z0-9_-]{0,63})(?:[ \t]+—[ \t]+([^\r\n]+))?[ \t]*$', re.MULTILINE)
GENERATED_REPORT_DIRECTORIES = frozenset({'benchmark-results', 'benchmark_results',
                                        'test-results', 'test_results', 'playwright-report'})


class ExtractionCapacityError(ExtractionContractError):
    """Adaptive processing reached the operator's packet allowance."""


class ExtractionNotAttempted(LLMError):
    """A previous sustained outage exhausted this phase's request allowance."""


def select_documents(capture, scope):
    selected, excluded = [], []
    for path in capture['documents']:
        generated = any(part.casefold() in GENERATED_REPORT_DIRECTORIES for part in Path(path).parts[:-1])
        if scope == 'project_docs' and generated:
            excluded.append({'path': path, 'reason': 'generated_report_directory'})
        else:
            selected.append(path)
    return {'scope': scope, 'selected_documents': selected, 'excluded_documents': excluded}


def custom_rules(path, value):
    matches = list(HEADING.finditer(value))
    if not matches:
        if value.strip():
            raise ValueError(f'{path}: use ## RULE-ID headings, or leave the file empty.')
        return []
    if value[:matches[0].start()].strip():
        raise ValueError(f'{path}: put each rule under a ## RULE-ID heading.')
    rules = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(value)
        statement = value[match.end():end].strip()
        title = match[2].strip() if match[2] else None
        if title and len(title.encode('utf-16-le')) // 2 > 120:
            raise ValueError(f'{path}: rule titles must be at most 120 characters.')
        if not statement or len(statement.encode()) > 4000:
            raise ValueError(f'{path}: each rule needs a statement of at most 4 KB.')
        rules.append({'id': match[1], 'statement': statement, 'origin': 'custom',
                      **({'title': title} if title else {}),
                      'source': {'path': path, 'start_line': value[:match.start()].count('\n') + 1,
                                 'end_line': value[:end].count('\n') or 1}})
    return rules


def markdown(rules):
    return '\n\n'.join(f"## {r['id']} — {r.get('title') or short_title(r['statement'])}\n\n{r['statement']}" for r in rules) + '\n'


def document_packets(index, path, value):
    # Complete physical lines, never a silent prefix of a specification.
    lines = value.splitlines(keepends=True)
    start, size = 1, 0
    for number, line in enumerate(lines, 1):
        if len(line.encode()) > 12_000:
            raise ValueError(f'{path}: documentation line exceeds 12 KB.')
        if size and (size + len(line.encode()) > 4000 or number - start >= 50):
            yield index.read(path, start, number - 1)
            start, size = number, 0
        size += len(line.encode())
    if lines:
        yield index.read(path, start, len(lines))


def exact_rule_source(index, packet, item):
    quote = item.get('quote')
    if not isinstance(quote, str) or not quote.strip():
        raise ExtractionContractError('Every rule needs a nonempty verbatim source quote.')
    position = packet['text'].find(quote)
    if position < 0 or packet['text'].find(quote, position + 1) >= 0:
        # A repeated quote may still be bound by an exact, bounded source span.
        start, end = item.get('start_line'), item.get('end_line')
        if (type(start) is int and type(end) is int
                and packet['start_line'] <= start <= end <= packet['end_line']):
            span = index.read(packet['path'], start, end)
            if quote in span['text']:
                return span
        raise ExtractionContractError('Every quote must occur verbatim in its numbered source lines; '
                                      'include more source context if the quote is repeated.')
    # Model line numbers are hints, not evidence. Derive physical lines from the
    # trusted captured text, preserving Unicode and CRLF/CR newline boundaries.
    start = end = None
    offset = 0
    for number, line in enumerate(packet['text'].splitlines(keepends=True), packet['start_line']):
        if offset <= position < offset + len(line):
            start = number
        if offset <= position + len(quote) - 1 < offset + len(line):
            end = number
            break
        offset += len(line)
    return index.read(packet['path'], start, end)


def packet_rules(index, packet, result):
    if result.get('complete') is not True or not isinstance(result.get('rules'), list):
        raise ExtractionContractError('Return the complete rules list and complete=true; do not omit rules.')
    admitted = {}
    for item in result['rules']:
        if not isinstance(item, dict):
            raise ExtractionContractError('Every extracted rule must be an object.')
        statement, quote = item.get('statement'), item.get('quote')
        span = exact_rule_source(index, packet, item)
        if (not isinstance(statement, str) or not statement.strip() or len(statement.encode()) > 4000
                or quote not in span['text'] or span['start_line'] < packet['start_line']
                or span['end_line'] > packet['end_line']):
            raise ExtractionContractError('Every rule needs a statement of at most 4 KB and an exact bounded source reference.')
        ident = 'GEN-' + sha256((packet['path'] + '\0' + statement.strip()).encode()).hexdigest()[:12]
        admitted[ident] = {'id': ident, 'statement': statement.strip(), 'origin': 'extracted',
                           'source': {k: v for k, v in span.items() if k != 'text'}, 'quote': quote}
    return admitted


def malformed_response(error):
    """Only a received, invalid model response permits format correction."""
    cause = error
    while cause is not None:
        if isinstance(cause, json.JSONDecodeError):
            return True
        cause = cause.__cause__
    return error.usage.get('provider_response_count', 0) > 0


def extraction_gap(packet, error):
    reason = ('not_attempted_after_model_failure' if isinstance(error, ExtractionNotAttempted) else
              'packet_budget' if isinstance(error, ExtractionCapacityError) else
              'extraction_deadline' if isinstance(error, TimeoutError) else
              'model_unavailable' if isinstance(error, LLMError) else 'invalid_model_response')
    result = {**{k: packet[k] for k in ('path', 'start_line', 'end_line', 'sha256', 'snapshot_id')},
              'status': 'unresolved', 'reason': reason}
    if isinstance(error, LLMError) and not isinstance(error, ExtractionNotAttempted):
        result['diagnostic'] = failure_details(error)
    return result


def stop_failed_extraction(block, result):
    if not result['rules'] and result.get('extraction_gaps'):
        gaps = result['extraction_gaps']
        save(block, 'extraction-status.json', {
            'schema': 'mn.software_rules.extraction_status.v1', 'status': 'failed',
            'reason': 'no_rules_extracted', 'rules': 0, 'unresolved_sections': len(gaps),
            'model_failed_sections': sum(gap['reason'] == 'model_unavailable' for gap in gaps),
            'unattempted_sections': sum(gap['reason'] == 'not_attempted_after_model_failure' for gap in gaps),
            'diagnostic_codes': sorted({gap['diagnostic']['code'] for gap in gaps
                                        if gap.get('diagnostic', {}).get('code')}),
            'verification_started': False,
            'message': "Couldn't extract software rules. Verification did not start.",
        })
        deliver_reports(block)
        require_rule_candidates(result)


def extract_packet(block, llm, index, packet, name, policy, deadline, budget):
    cache = f'extraction/{name}.json'
    if block.store.path(cache).is_file():
        result = read(block, cache)
        packet_rules(index, packet, result)
        return result
    def validate(result):
        return packet_rules(index, packet, result)
    try:
        checkpoint = rule_cache.load(block, packet, validate)
    except (ValueError, KeyError, OSError):
        save(block, f'extraction/cache-rejected/{name.replace("/", "-")}.json',
             {'status': 'recompute', 'reason': 'checkpoint_validation_failed'})
        checkpoint = None
    if checkpoint is not None:
        save(block, cache, checkpoint['response'])
        save(block, f'extraction/reused/{name.replace("/", "-")}.json',
             {key: checkpoint[key] for key in ('identity', 'producer_run_id')})
        return checkpoint['response']
    feedback, pending, indices = None, None, []
    for attempt in range(policy['max_extraction_attempts']):
        block.check()
        if time.monotonic() >= deadline:
            raise TimeoutError('Extraction deadline reached before source validation completed.')
        request = {'document': {**packet, 'numbered_lines': source_lines(packet)}}
        if feedback:
            request['correction'] = feedback
        if pending is not None:
            request['rules_to_correct'] = [{'index': i, 'statement': pending['rules'][i].get('statement')}
                                           for i in indices]
        split = False
        try:
            result = ask(llm, 'repair_sources.md' if pending is not None else 'extract.md', request)
        except LLMError as error:
            if not malformed_response(error):
                save(block, f'extraction/drafts/{name.replace("/", "-")}-attempt-{attempt + 1}.json',
                     {'error': 'model_unavailable', 'diagnostic': failure_details(error)})
                feedback = None
                if attempt + 1 < policy['max_extraction_attempts']:
                    time.sleep(min(2 ** attempt, max(0, deadline - time.monotonic())))
                    continue
                raise
            save(block, f'extraction/drafts/{name.replace("/", "-")}-attempt-{attempt + 1}.json',
                 {'error': 'invalid_json', 'output_tokens': error.usage.get('output_tokens')})
            feedback = 'Return one complete, compact JSON object. The previous response was invalid JSON.'
            split = True
        else:
            save(block, f'extraction/drafts/{name.replace("/", "-")}-attempt-{attempt + 1}.json', result)
            split = result.get('complete') is False and isinstance(result.get('rules'), list)
            if not split:
                try:
                    if pending is not None:
                        result = apply_source_repairs(pending, indices, result)
                    raw = result
                    result = bind_sources(index, packet, result)
                    packet_rules(index, packet, result)
                except SourceSelectionError as error:
                    pending, indices = raw, error.indices
                    feedback = str(error)
                except ExtractionContractError as error:
                    feedback = str(error)
                else:
                    save(block, cache, result)
                    try:
                        rule_cache.store(block, packet, result, validate)
                    except OSError:
                        pass  # Optional acceleration cannot prevent durable run output.
                    return result
            else:
                feedback = 'Return the complete rules list; partial extraction cannot be admitted.'
        if attempt + 1 == policy['max_extraction_attempts'] and policy['max_extraction_attempts'] > 1:
            split = True  # Persistent output errors also get smaller, independently validated source packets.
        if split and packet['start_line'] < packet['end_line']:
            split_name = f'extraction/splits/{name.replace("/", "-")}.json'
            identity = {k: packet[k] for k in ('path', 'start_line', 'end_line', 'sha256', 'snapshot_id')}
            if block.store.path(split_name).is_file():
                if read(block, split_name) != identity:
                    raise ValueError('Saved extraction split does not match the captured source.')
            else:
                if budget['packets'] + 2 > policy['max_extraction_packets']:
                    raise ExtractionCapacityError('Adaptive extraction reached review.max_extraction_packets.')
                save(block, split_name, identity)
                budget['packets'] += 2
            middle = (packet['start_line'] + packet['end_line']) // 2
            parts = [index.read(packet['path'], packet['start_line'], middle),
                     index.read(packet['path'], middle + 1, packet['end_line'])]
            children, gaps = [], []
            # Smaller complete-line packets partition the same captured evidence.
            # Never accept a partial parent response or repair/truncate its text.
            for suffix, part in zip(('left', 'right'), parts):
                try:
                    child = extract_packet(block, llm, index, part,
                        f'parts/{Path(name).name}-{suffix}', policy, deadline, budget)
                except (ExtractionContractError, LLMError, TimeoutError) as error:
                    gap = extraction_gap(part, error)
                    gaps.append(gap)
                    save(block, f'extraction/unresolved/{Path(name).name}-{suffix}.json', gap)
                    continue
                children.extend(child['rules'])
                gaps.extend(child.get('extraction_gaps', []))
            result = {'complete': True, 'rules': children}
            if gaps:
                result['extraction_gaps'] = gaps
            packet_rules(index, packet, result)
            save(block, cache, result)
            if not gaps:
                try:
                    rule_cache.store(block, packet, result, validate)
                except OSError:
                    pass
            return result
    raise ExtractionContractError(
        f'{name} failed extraction after {policy["max_extraction_attempts"]} attempts. '
        'Draft responses remain in extraction/drafts; this source section requires review.')


def extract(block, inputs, *, llm=None):
    report_activity("Extracting software rules", owner_blueprint=BLUEPRINT_ID,
                    step_id=block.step_id, run_dir=block.store.run_dir)
    capture_ref = inputs["previous"]["capture"]
    capture = block.store.read(capture_ref)
    llm = llm or block.resources.get("llm")
    policy = settings(block)
    deadline = time.monotonic() + policy['extraction_timeout_seconds']
    if block.store.path('rules.json').is_file():
        result = read(block, 'rules.json')
        stop_failed_extraction(block, result)
        return {'rules': len(result['rules']), 'capture': capture_ref}
    sources = capture['sources']
    index, custom = TextSearchIndex(sources), {}
    for path in capture['custom_documents']:
        for rule in custom_rules(path, sources[path]):
            if rule['id'] in custom:
                raise ValueError('Custom rule IDs must be unique across knowledge files.')
            custom[rule['id']] = rule
    mode = policy['rules_mode']
    if mode not in {'augment', 'replace'}:
        raise ValueError('rules_mode must be augment or replace.')
    rules, receipts, gaps = {}, [], []
    selection = {'scope': 'custom_rules_only', 'selected_documents': [], 'excluded_documents': []}
    if mode == 'augment':
        selection = select_documents(capture, policy['documentation_scope'])
        packets = []
        for path in selection['selected_documents']:
            for packet in document_packets(index, path, sources[path]):
                packets.append(packet)
                if len(packets) > policy['max_extraction_packets']:
                    raise ValueError(f"Selected documentation exceeds review.max_extraction_packets="
                                     f"{policy['max_extraction_packets']}. Choose project docs, "
                                     'increase the packet budget, or narrow the source folder.')
        save(block, 'extraction-plan.json', {**selection, 'packet_count': len(packets),
             'max_extraction_packets': policy['max_extraction_packets'], 'snapshot_id': index.snapshot_id})
        llm = llm or client(extraction=True)
        split_count = len(list(block.store.path('extraction/splits').glob('*.json')))
        budget = {'packets': len(packets) + 2 * split_count}
        if budget['packets'] > policy['max_extraction_packets']:
            raise ValueError('Saved extraction exceeds review.max_extraction_packets.')
        unavailable = 0
        for number, packet in enumerate(packets):
            block.check()
            report_activity(f'Reading document packet {number + 1} of {len(packets)}',
                            kind='action', run_dir=block.store.run_dir, owner_blueprint=BLUEPRINT_ID)
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Extraction deadline reached.')
                if unavailable >= 3:
                    raise ExtractionNotAttempted('Model requests remain unavailable.')
                result = extract_packet(block, llm, index, packet, f'packet-{number:04}', policy, deadline, budget)
                admitted = packet_rules(index, packet, result)
            except (ExtractionContractError, LLMError, TimeoutError) as error:
                unavailable = unavailable + 1 if isinstance(error, LLMError) else 0
                gap = extraction_gap(packet, error)
                gaps.append(gap)
                save(block, f'extraction/unresolved/packet-{number:04}.json', gap)
                receipts.append(gap)
                report_activity('A document section needs review. Continuing with the remaining documents.',
                                kind='action', run_dir=block.store.run_dir, owner_blueprint=BLUEPRINT_ID)
                continue
            unavailable = 0
            gaps.extend(result.get('extraction_gaps', []))
            rules.update(admitted)
            receipts.append({'path': packet['path'], 'start_line': packet['start_line'], 'end_line': packet['end_line']})
    rules.update(custom)  # A copied generated ID is an explicit supervisor override.
    result = {'schema_version': 'mn.software_rules.rules.v1', 'snapshot_id': index.snapshot_id,
              'mode': mode, 'rules': list(rules.values()), 'extraction_coverage': receipts}
    result['documentation_selection'] = selection
    result['extraction_gaps'] = gaps
    result['extraction_status'] = ('failed' if gaps and not rules else 'needs_review' if gaps
                                   else 'complete' if rules else 'no_rules')
    result['verification_rule_limit'] = policy['max_rules']
    text(block, 'rules.md', markdown(result['rules']))
    save(block, 'rules.json', result)
    stop_failed_extraction(block, result)
    return {'rules': len(rules), 'extraction_status': result['extraction_status'],
            'unresolved_sections': len(gaps), 'capture': capture_ref}
