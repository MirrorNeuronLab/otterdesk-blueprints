"""Research-only CT report policy and publication from a verified native result."""

import hashlib
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.context_engine import context_memory_section_enabled
from mn_sdk.integrations.block_publication_files import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

NOTICE = 'Research and education only. Not for real diagnosis, treatment, or clinical decisions. Model output may be incorrect.'
LIMITATIONS = ['Only the anatomy-aware model crop is interpreted; the preview shows the original volume.',
    'No clinical validation, calibrated confidence, or guarantee of complete scan coverage.']


def publish(block, data):
    request, result = data["request"]["payload"], data["result"]
    source = request["volume_base64"]["$artifact"]
    block.store.validate(source)
    saved = {'schema': 'mn.ct.research_report.v1', 'research_only': True, 'notice': NOTICE,
        'input_sha256': source['sha256'], 'region': request['region'], 'prompt': request['prompt'],
        'model': source_manifest(__file__)['runtime']['models']['ct']['model'],
        'model_revision': result['model_revision'], 'answer': result['answer'].strip(), 'limitations': LIMITATIONS}
    captured = block.store.read_path('inputs.json')
    saved['supervisor_instruction_revision'] = fingerprint(captured.get('supervisor_instructions', []))
    report = block.store.commit('final_artifact.json', saved, kind='ct_research_report')
    markdown = '# Experimental CT report\n\n' + NOTICE + '\n\n' + saved['answer'] + \
        '\n\n## Limitations\n\n' + '\n'.join('- ' + item for item in LIMITATIONS) + '\n'
    text = block.store.commit_bytes('report.md', markdown.encode(), kind='markdown')
    writes = [
        ArtifactWrite('ct_research_report', 'final_artifact.json', block.store.read_bytes(report),
            kind='ct_research_report', authoritative=True),
        ArtifactWrite('report', 'report.md', block.store.read_bytes(text), kind='markdown'),
    ]
    if context_memory_section_enabled(block.config.get('source_context') or {}):
        writes.append(ArtifactWrite('conversation-report', 'context_sources/outputs/' + hashlib.sha256(block.run_id.encode()).hexdigest() + '/report.md',
            ('Run reference: ' + block.run_id + '\nRegion: ' + saved['region'] + '\nModel revision: ' + saved['model_revision']
             + '\nInput SHA-256: ' + saved['input_sha256'] + '\n\n' + markdown).encode(), kind='markdown'))
    publish_artifact_bundle(block, writes, receipt_path=block.root + '/publication.json')
    return {'research_only': True, 'report': report.to_dict(), 'notice': NOTICE,
        'artifacts': [report.to_dict(), text.to_dict()]}
