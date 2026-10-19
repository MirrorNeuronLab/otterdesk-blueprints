"""An unsuccessful extraction cannot authorize an empty verification run."""


class RuleExtractionFailed(RuntimeError):
    """No rule candidates survived extraction of the selected documents."""


def require_rule_candidates(rules):
    if not rules['rules'] and rules.get('extraction_gaps'):
        raise RuleExtractionFailed(
            "Couldn't extract software rules. Verification did not start. "
            'Review extraction-status.json and try again.')
