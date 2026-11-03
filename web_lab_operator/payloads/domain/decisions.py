"""One SDK-journaled model decision grounded in the current simulated state."""

import json
from pathlib import Path

from mn_sdk.integrations.block_model_request import model_request

from .protocol import candidates

DECISION_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['step_id', 'decision', 'source', 'reason'],
    'properties': {
        'step_id': {'type': 'string'},
        'decision': {'type': 'string', 'enum': ['execute', 'adapt', 'pause']},
        'source': {'type': 'string'}, 'reason': {'type': 'string'},
    },
}


def choose(block, step, observed, previous, history):
    llm = block.config['llm']
    user = {'step': step, 'observed': observed, 'allowed_sources': candidates(step, observed),
            'previous_outcome': previous, 'runtime_memory': history}
    response = model_request(block, {
        'purpose': 'web_lab_operator', 'model': llm['model'], 'path': '/chat/completions',
        'payload': {'messages': [
            {'role': 'system', 'content': (Path(__file__).resolve().parents[1] / 'prompts/adapt.md').read_text()},
            {'role': 'user', 'content': json.dumps(user, ensure_ascii=False, allow_nan=False)}],
            'max_tokens': 700, 'temperature': 0,
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'lab_decision', 'strict': True, 'schema': DECISION_SCHEMA}}},
        'options': {'provider': llm.get('provider', 'docker_model_runner'),
                    'timeout_seconds': 60, 'structured_output': True},
    }, key='decision:' + step['id'])
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices or choices[0].get('finish_reason') != 'stop':
        raise ValueError("The model did not return a complete lab decision.")
    content = choices[0].get('message', {}).get('content')
    if not isinstance(content, str) or len(content.encode()) > 8000:
        raise ValueError("The lab decision exceeds its text limit.")
    return json.loads(content)
