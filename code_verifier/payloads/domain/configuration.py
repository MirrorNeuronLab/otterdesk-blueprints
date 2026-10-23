"""Bound operator tunables before any source/model work."""

from mn_sdk.blueprint_support import source_manifest

BLUEPRINT_ID = source_manifest(__file__)["metadata"]["blueprint_id"]


def settings(block):
    values = block.config['review']
    for name, maximum in [('max_rules', 2000), ('max_turns_per_rule', 12),
                          ('max_extraction_packets', 2048),
                          ('max_extraction_attempts', 3),
                          ('human_review_timeout_seconds', 3600)]:
        value = values.get(name)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f'{name} must be an integer in 1..{maximum}.')
    for name in ('extraction_timeout_seconds', 'verification_timeout_seconds'):
        value = values.get(name)
        if value is not None and (type(value) is not int or not 1 <= value <= 3600):
            raise ValueError(f'{name} must be null or an integer in 1..3600.')
    if values.get('rules_mode') not in {'augment', 'replace'}:
        raise ValueError('rules_mode must be augment or replace.')
    if values.get('documentation_scope') not in {'project_docs', 'all_captured_docs'}:
        raise ValueError('documentation_scope must be project_docs or all_captured_docs.')
    return values


def phase_deadline(policy, name):
    import time
    allowance = policy[name]
    return float('inf') if allowance is None else time.monotonic() + allowance
