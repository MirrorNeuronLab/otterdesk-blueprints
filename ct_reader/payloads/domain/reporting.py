"""Research-only CT report policy and publication from a verified native result."""

from mn_sdk.blueprint_support import source_manifest

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
    report = block.store.commit('final_artifact.json', saved, kind='ct_research_report')
    markdown = '# Experimental CT report\n\n' + NOTICE + '\n\n' + saved['answer'] + \
        '\n\n## Limitations\n\n' + '\n'.join('- ' + item for item in LIMITATIONS) + '\n'
    text = block.store.commit_bytes('report.md', markdown.encode(), kind='markdown')
    return {'research_only': True, 'report': report.to_dict(), 'notice': NOTICE,
        'artifacts': [report.to_dict(), text.to_dict()]}
