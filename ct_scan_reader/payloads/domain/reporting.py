"""One experimental inference; durable results before bounded coordination output."""
import base64
import hashlib
import json
from pathlib import Path

from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import source_manifest, write_json
from mn_sdk.model_access.runtime import runtime_model_json_request
from mn_sdk.step_runtime import artifact_reference

NOTICE = 'Research and education only. Not for real diagnosis, treatment, or clinical decisions. Model output may be incorrect.'
MAX_CT_BYTES = 64 * 1024 * 1024


@activity_operation('Reading CT for research', completed='Experimental CT report saved for review')
def review_ct(context, request=runtime_model_json_request):
    run_dir = Path(context['run_dir'])
    inputs = context.get('payload') or context.get('inputs') or context.get('config', {}).get('inputs', {}).get('payload', {})
    source = Path(inputs.get('ct_file') or '')
    region = inputs.get('region')
    prompt = str(inputs.get('prompt') or f'write a structured {"abdominal" if region == "abdomen" else "chest"} CT report')
    if region not in ('chest', 'abdomen') or not source.is_file() or source.stat().st_size > MAX_CT_BYTES:
        raise ValueError('A bounded CT file and matching chest or abdomen region are required.')
    if not 0 < len(prompt) <= 2000:
        raise ValueError('Keep the research question under 2,000 characters.')
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    manifest = source_manifest(__file__)
    model = manifest['runtime']['models']['ct']
    target = run_dir / 'final_artifact.json'
    if target.exists():
        saved = json.loads(target.read_text())
        if saved.get('input_sha256') != digest or saved.get('region') != region or saved.get('prompt') != prompt:
            raise ValueError('This invocation already has a result for different inputs.')
    else:
        result = request('vlm', model['model'], '/ct', {
            'volume_base64': base64.b64encode(data).decode('ascii'), 'region': region, 'prompt': prompt,
        }, provider=model['provider'], backend=model['backend'], model_spec=model['model_spec'],
            timeout_seconds=600, num_retries=0)
        answer = result.get('answer')
        if not isinstance(answer, str) or not 0 < len(answer.strip()) <= 32000 or result.get('research_only') is not True:
            raise ValueError('NV-Reason-CT did not return a valid experimental report.')
        saved = {'schema': 'mn.ct.research_report.v1', 'research_only': True, 'notice': NOTICE,
            'input_sha256': digest, 'region': region, 'prompt': prompt, 'model': model['model'],
            'model_revision': result['model_revision'], 'answer': answer.strip(),
            'limitations': ['Only the anatomy-aware model crop is interpreted; the preview shows the original volume.',
                'No clinical validation, calibrated confidence, or guarantee of complete scan coverage.']}
        write_json(target, saved)
    # Recover a report write interrupted after the authoritative JSON commit.
    report = run_dir / 'report.md'
    report.write_text('# Experimental CT report\n\n' + NOTICE + '\n\n' + saved['answer'] +
        '\n\n## Limitations\n\n' + '\n'.join('- ' + item for item in saved['limitations']) + '\n')
    references = [artifact_reference('ct_research_report', 'final_artifact.json'), artifact_reference('report', 'report.md')]
    return {'research_only': True, 'report': references[0], 'notice': NOTICE}, references
