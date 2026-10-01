"""Retry allowances layered over immutable architecture evidence and requests."""
import time
from mn_sdk.run_retry import effective_configuration, remaining_seconds, retry_context


def effective_config(original, *, paths=None):
    retry = retry_context()
    if paths is not None:
        retry = {**retry, 'configuration_overrides': {path: value for path, value in retry.get('configuration_overrides', {}).items() if path in paths}}
    return effective_configuration(original, retry)


def effective_deadline(original_deadline, allowance):
    retry = retry_context()
    if not retry:
        return original_deadline
    return time.time() + remaining_seconds(allowance, retry)
