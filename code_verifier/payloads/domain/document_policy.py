"""Section-aware current-requirement scope; excluded text remains auditable."""
from hashlib import sha256
from pathlib import PurePosixPath
from pathlib import Path
import re

from .source_policy import GENERATED

POLICY = 'current-scoped-requirements-v2'
NORMATIVE = re.compile(r'\b(must|shall|should|may|required|requires|never|cannot|only)\b|\bdo not\b', re.I)


def document_reason(path, scope):
    parts = [part.casefold() for part in PurePosixPath(path).parts]
    if scope != 'all_captured_docs' and any(p in GENERATED for p in parts[:-1]):
        return 'generated_report_directory'
    if scope == 'current_requirements':
        if parts[-1].startswith(('changelog', 'changes', 'history', 'release-notes')):
            return 'historical_changes'
        if any(p in {'evaluations', 'evaluation-results', 'archives', 'archive'} for p in parts[:-1]) or re.search(
                r'(live-benchmark|benchmark-review|native-context-validation|release-validation)[-_\d]', parts[-1]):
            return 'historical_evaluation'
    return None


def line_contexts(text, *, current=True):
    heading, fence, tutorial = [], None, False
    contexts = {}
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        inside = fence is not None
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = None
            inside = True
        match = re.match(r'^(#{1,6})\s+(.+)', line) if not inside else None
        if match:
            level, title = len(match[1]), match[2].strip()
            heading = [(n, t) for n, t in heading if n < level] + [(level, title)]
            tutorial = any(re.search(r'\b(quick\s*start|tutorial|getting started|get a first response|example)\b', t, re.I)
                           for _, t in heading)
        reason = ('example_code' if inside else
                  'tutorial_instruction' if current and tutorial and line.strip() and not NORMATIVE.search(line) else None)
        contexts[number] = {'heading': [t for _, t in heading], 'in_code_fence': inside,
                            'eligible': reason is None, 'reason': reason}
    return contexts


def annotate(packet, contexts, text):
    lines = text.splitlines(keepends=True)
    start, end = packet['start_line'], packet['end_line']
    previous, size = [], 0
    cursor = start - 2
    while cursor >= 0 and len(previous) < 12:
        line = lines[cursor]
        if size + len(line.encode()) > 4000:
            break
        previous.insert(0, line)
        size += len(line.encode())
        cursor -= 1
        if not line.strip():
            break
    return {**packet, 'line_context': {str(n): contexts[n] for n in range(start, end + 1)},
            'preceding_context': ''.join(previous),
            'preceding_context_complete': cursor < 0 or bool(previous and not previous[0].strip())}


def excluded_sections(index, path, contexts):
    groups = []
    for number, context in contexts.items():
        reason = context['reason']
        if reason:
            if groups and groups[-1]['reason'] == reason and groups[-1]['end_line'] == number - 1:
                groups[-1]['end_line'] = number
            else:
                groups.append({'path': path, 'start_line': number, 'end_line': number, 'reason': reason})
    for group in groups:
        span = index.read(path, group['start_line'], group['start_line'])
        group.update({k: span[k] for k in ('sha256', 'snapshot_id')})
    return groups


def policy_identity():
    root = Path(__file__).parent
    files = [root / name for name in ('document_policy.py', 'rule_sources.py', 'rules.py')]
    files += [root.parent / 'prompts' / name for name in ('extract.md', 'repair_sources.md')]
    return POLICY + ':' + sha256(b''.join(path.read_bytes() for path in files)).hexdigest()


def consolidate(rules):
    """Merge exact scoped duplicates only; flag potential conflicts, never resolve them."""
    unique, flags, signatures = {}, [], {}
    for rule in rules:
        if rule['origin'] != 'extracted':
            unique[rule['id']] = rule
            continue
        statement = rule['statement'].strip()
        scope = (rule.get('subject', ''), rule.get('scope', 'product'), rule.get('modality', ''),
                 tuple(rule.get('conditions', [])), rule.get('requirement_kind', 'behavior'))
        key = (statement, scope)
        previous = signatures.get(key)
        if previous:
            previous.setdefault('additional_origins', []).append({'id': rule['id'], 'source': rule['source'], 'quote': rule.get('quote', '')})
        else:
            unique[rule['id']] = rule
            signatures[key] = rule
    possible = {}
    for rule in unique.values():
        normalized = re.sub(r'\b(must|shall|should|not|never|may)\b', '', rule['statement'].casefold())
        key = (rule.get('scope', 'product'), ' '.join(normalized.split()))
        possible.setdefault(key, []).append(rule['id'])
    for group in possible.values():
        if len(group) > 1:
            flags.append({'kind': 'similar_or_conflicting_rules', 'rule_ids': group})
    return list(unique.values()), flags
