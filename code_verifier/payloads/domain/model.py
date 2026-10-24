"""Strict SDK model calls; no generated or deterministic success substitution."""
import json
from pathlib import Path
import re

from mn_sdk.llm import LLMClient
from mn_sdk.model_access.errors import ModelAccessError

from .model_contracts import response_schema


def client(*, extraction=False):
    result = LLMClient.from_env(strict=True)
    # Preparation owns the model, provider, endpoint, credentials and options
    # as one binding. Blueprint defaults must not overwrite its resolved route.
    result.max_tokens = 8192 if extraction else 3500
    result.timeout_seconds = 90
    result.num_retries = 0
    return result


def ask(llm, prompt, packet):
    system = (Path(__file__).parents[1] / 'prompts' / prompt).read_text(encoding='utf-8')
    encoded = json.dumps(packet, ensure_ascii=False)
    if len(encoded.encode()) > 100_000:
        raise ValueError('Model evidence packet exceeds 100 KB; select a smaller source scope.')
    result = llm.generate_json(system_prompt=system, user_prompt=encoded, fallback=None,
        response_schema=response_schema(prompt), schema_name='software_review_response')
    if not isinstance(result, dict):
        raise ValueError('Model did not return a JSON object.')
    return result


def failure_details(error):
    """Retain typed diagnostic fields, never provider text, requests or sources."""
    usage = getattr(error, 'usage', {})
    count = usage.get('provider_response_count', 0) if isinstance(usage, dict) else 0
    result = {'error_type': type(error).__name__,
              'provider_response_count': count if type(count) is int and 0 <= count <= 100 else 0}
    seen = set()
    for _ in range(8):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        if isinstance(error, ModelAccessError):
            for key in ('code', 'stage'):
                value = getattr(error, key, '')
                if isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_.-]{0,95}', value):
                    result[key] = value
            result['retryable'] = error.retryable is True
            break
        error = error.__cause__
    return result
