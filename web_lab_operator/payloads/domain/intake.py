"""Freeze the supplied Markdown through the shared run-input and artifact contracts."""

import hashlib
from pathlib import Path

from mn_sdk.integrations.block_inputs import capture_declared_inputs

from .memory import LabMemory
from .protocol import numbered_instructions


def capture(block, inputs):
    values = capture_declared_inputs(block, inputs, runtime_file=__file__)
    markdown, filename = values.get('procedure_markdown', ''), values.get('procedure_file', '')
    if not isinstance(markdown, str) or not isinstance(filename, str):
        raise ValueError("Provide Markdown text or a staged Markdown file path.")
    if bool(markdown.strip()) == bool(filename):
        raise ValueError("Provide Markdown text or a Markdown file, using one input.")
    if filename:
        path = Path(filename)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != '.md':
            raise ValueError("Choose a regular UTF-8 Markdown (.md) procedure file.")
        with path.open('rb') as source:
            content = source.read(32001)
        if len(content) > 32000:
            raise ValueError("The procedure exceeds 32,000 UTF-8 bytes.")
        markdown = content.decode('utf-8')
    if not isinstance(markdown, str) or not 1 <= len(markdown.encode('utf-8')) <= 32000 or '\x00' in markdown:
        raise ValueError("Supply a nonempty Markdown procedure within 32,000 UTF-8 bytes.")
    reference = block.store.commit_bytes('procedure.md', markdown.encode('utf-8'), kind='markdown')
    identity = hashlib.sha256(markdown.encode()).hexdigest()
    with LabMemory(block, identity) as memory:
        history, witness = memory.recall('planning')
    return {'markdown': markdown, 'sha256': identity,
            'numbered_instructions': numbered_instructions(markdown),
            'procedure': reference.to_dict(), 'mode': 'simulation_only',
            'runtime_memory': history, 'memory_recall': witness,
            'supported_labware': '1..4 96-well 360 uL plates; 96 fresh 300 uL tips; one channel',
            'supported_steps': ['transfer', 'mix', 'wait', 'check_volume']}
