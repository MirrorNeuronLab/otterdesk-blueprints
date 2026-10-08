"""Verbatim legal units and explicit local clause/definition dependencies.

This is structural navigation. It does not decide enforceability, amendment
precedence, identity, or whether a quoted statement is true.
"""
from dataclasses import replace
import hashlib
import re

from mn_context_engine_sdk.intelligent_system import TextDocumentAdapter, SourceSection
from mn_context_engine_sdk.intelligent_system.sources import validate_sections

VERSION = 'legal-source-structure/1'
NUMBER = re.compile(r'^\s*(?:Section\s+)?(\d+(?:\.\d+)*)(?:\.)?\s+', re.I)
REFERENCE = re.compile(r'\bSections?\s+(\d+(?:\.\d+)*(?:\s*(?:,|and|or|through|to|[-–])\s*\d+(?:\.\d+)*)*)', re.I)
DEFINITION = re.compile(r'["“]([^"”\n]{1,120})["”]\s+(?:shall\s+)?(?:means?|includes?)\b', re.I)


class LegalSourceAdapter(TextDocumentAdapter):
    def __init__(self):
        super().__init__()
        self.coverage = {}

    def sections(self, text, path):
        parts = super().sections(text, path)
        body = text.encode()
        # Paragraph breaks inside one numbered clause do not split its provisos.
        grouped = []
        for part in parts:
            value = body[part.start_byte:part.end_byte].decode()
            number = NUMBER.match(value)
            if grouped and grouped[-1][2] and not number:
                grouped[-1][1] = part.end_byte
            else:
                grouped.append([part.start_byte, part.end_byte, number.group(1) if number else None])
        sections, content, numbers, definitions = [], {}, {}, {}
        for a, b, number in grouped:
            value = body[a:b].decode()
            first = body[:a].decode().count('\n') + 1
            name = f'{path} unit {len(sections)+1}'
            section = SourceSection(name, first, first + value.rstrip('\n').count('\n'),
                'verbatim_legal_unit_not_established_fact',
                'sha256:' + hashlib.sha256(value.encode()).hexdigest(), a, b)
            sections.append(section); content[name] = value
            if number:
                numbers.setdefault(number, []).append(name)
            for term in DEFINITION.findall(value):
                definitions.setdefault(term, []).append(name)
        unresolved, result = [], []
        for section, (_, _, number) in zip(sections, grouped):
            value = content[section.name]
            dependencies = []
            # A numbered parent and its subclauses are one qualification group.
            if number:
                parent = number.rpartition('.')[0]
                dependencies.extend(numbers.get(parent, []))
                dependencies.extend(name for key, names in numbers.items() if key.startswith(number + '.') for name in names)
            for match in REFERENCE.finditer(value):
                reference = match.group(1)
                suffix = value[match.end():match.end()+80]
                external = re.match(r'\s+of\s+(?!this\b|herein\b)', suffix, re.I)
                ranged = re.search(r'\bthrough\b|\bto\b|[-–]', reference, re.I)
                if external or ranged:
                    unresolved.append({'unit':section.name,'reference':match.group(),
                        'status':'external_reference' if external else 'reference_range_unresolved'})
                    continue
                for number_ref in re.findall(r'\d+(?:\.\d+)*', reference):
                    if number_ref in numbers:
                        dependencies.extend(numbers[number_ref])
                    else:
                        unresolved.append({'unit': section.name, 'reference': number_ref,
                                           'status': 'unresolved_or_external_reference'})
            for term, names in definitions.items():
                if re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', value):
                    dependencies.extend(names)
            dependencies = tuple(dict.fromkeys(n for n in dependencies if n != section.name))
            if len(dependencies) > 128:
                raise ValueError('Legal source dependency capacity exceeded; partition the input explicitly')
            result.append(replace(section, dependencies=dependencies))
        # Rank the final structural units, not their superseded paragraph pieces.
        from mn_context_engine_sdk.intelligent_system.text_documents import _terms
        for part in parts:
            self._terms.pop(part, None)
        for section in result:
            self._terms[section] = _terms(content[section.name])
        self._statistics = None
        self.coverage[path] = {'version': VERSION, 'unresolved': unresolved,
                               'qualification': 'Explicit local references only; legal effect is not inferred.'}
        validate_sections(text, result)
        return result


def structured_units(document):
    adapter = LegalSourceAdapter()
    sections = adapter.sections(document.text, document.relative_path)
    body = document.text.encode()
    values = []
    for section in sections:
        a, b = section.start_byte, section.end_byte
        values.append({'name': section.name, 'start_offset': len(body[:a].decode()),
            'end_offset': len(body[:b].decode()), 'text': body[a:b].decode(),
            'dependencies': list(section.dependencies)})
    return values, adapter.coverage[document.relative_path]
