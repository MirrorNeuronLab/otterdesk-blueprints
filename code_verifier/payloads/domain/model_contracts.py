"""Wire shapes for model decisions; evidence admission remains domain-owned."""


def object_schema(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def response_schema(prompt):
    text = {'type': 'string', 'minLength': 1}
    sources = {'type': 'array', 'minItems': 1, 'items': text}
    if prompt == 'extract.md':
        return object_schema({
            'complete': {'type': 'boolean', 'enum': [True, False]},
            'rules': {'type': 'array', 'items': object_schema({
                'statement': {**text, 'maxLength': 4000}, 'source_ids': sources})},
        })
    if prompt == 'repair_sources.md':
        return object_schema({'repairs': {'type': 'array', 'items': object_schema({
            'index': {'type': 'integer', 'minimum': 0}, 'source_ids': sources})}})
    if prompt == 'verify.md':
        return {'anyOf': [
            object_schema({'action': {'const': 'finish'},
                'status': {'enum': ['unknown', 'pass', 'fail']},
                'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'explanation': {**text, 'maxLength': 6000},
                'evidence_ids': {'type': 'array', 'maxItems': 12, 'items': text}}),
            object_schema({'action': {'const': 'search'}, 'query': text}),
            object_schema({'action': {'const': 'read'}, 'path': text,
                'start_line': {'type': 'integer', 'minimum': 1},
                'end_line': {'type': 'integer', 'minimum': 1}}),
        ]}
    raise ValueError('Unknown software review model contract.')
