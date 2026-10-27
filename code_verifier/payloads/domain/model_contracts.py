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
                'statement': {**text, 'maxLength': 4000}, 'source_ids': sources,
                'subject': {**text, 'maxLength': 500}, 'scope': {**text, 'maxLength': 500},
                'modality': {'type': 'string', 'enum': ['must', 'should', 'may', 'descriptive']},
                'conditions': {'type': 'array', 'maxItems': 8, 'items': {**text, 'maxLength': 500}},
                'requirement_kind': {'type': 'string', 'enum': ['behavior', 'configuration', 'source_structure']}})},
        })
    if prompt == 'repair_sources.md':
        return object_schema({'repairs': {'type': 'array', 'items': object_schema({
            'index': {'type': 'integer', 'minimum': 0}, 'source_ids': sources})}})
    if prompt in {'verify.md', 'judge.md', 'critique.md'}:
        # Strict model routes require an object at the schema root. Keep the
        # action union inside that object, with explicit types on every branch.
        finish = object_schema({'action': {'type': 'string', 'enum': ['finish']},
                'status': {'type': 'string', 'enum': ['unknown', 'pass', 'fail']},
                'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'explanation': {**text, 'maxLength': 6000},
                'evidence_ids': {'type': 'array', 'maxItems': 12, 'items': text},
                'assessment': object_schema({
                    'support': {'type': 'string', 'enum': ['unresolved', 'supported', 'contradicted']},
                    'scope_matches': {'type': 'boolean'}, 'conditions_checked': {'type': 'boolean'},
                    'requirement_kind': {'type': 'string', 'enum': ['behavior', 'configuration', 'source_structure']},
                    'enforcement_evidence_ids': {'type': 'array', 'maxItems': 12, 'items': text},
                    'missing_evidence': {'type': 'string', 'maxLength': 2000},
                    'reason_code': {'type': 'string', 'enum': ['insufficient_evidence', 'parser_gap', 'capture_gap',
                        'ambiguous_rule', 'runtime_evidence_required']}})})
        if prompt != 'verify.md':
            return object_schema({'decision': finish})
        return object_schema({'decision': {'anyOf': [finish,
            object_schema({'action': {'type': 'string', 'enum': ['search']}, 'query': text}),
            object_schema({'action': {'type': 'string', 'enum': ['rank']}, 'query': text}),
            object_schema({'action': {'type': 'string', 'enum': ['symbols']}, 'query': text}),
            object_schema({'action': {'type': 'string', 'enum': ['trace']}, 'symbol': text,
                'depth': {'type': 'integer', 'minimum': 1, 'maximum': 3}}),
            object_schema({'action': {'type': 'string', 'enum': ['read']}, 'path': text,
                'start_line': {'type': 'integer', 'minimum': 1},
                'end_line': {'type': 'integer', 'minimum': 1}}),
        ]}})
    raise ValueError('Unknown software review model contract.')
