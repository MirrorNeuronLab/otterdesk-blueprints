"""Measured model-stage timing; unavailable provider internals stay unknown."""
import json


def measure(root):
    from mn_sdk.resource_usage_ledger import merge_model_measurements
    from mn_sdk.job_analysis import usage_totals
    samples, ledger = merge_model_measurements(root, [])
    provider_usage = usage_totals([{'type':'llm_usage', 'event_id':str(i), 'payload':s['llm']}
        for i,s in enumerate(samples) if 'llm' in s]) if ledger else None
    stages = []
    for path in sorted((root / 'case/rounds/timing').glob('*.json')):
        stages.append(json.loads(path.read_text()))
    totals = {'input_tokens':0, 'output_tokens':0, 'total_tokens':0, 'provider_response_count':0}
    measured = 0
    responses = []
    for path in sorted((root / 'case/rounds/models').glob('*.json')):
        value = json.loads(path.read_text())
        usage = value.get('usage', {})
        if 'value' in value:
            responses.append({'decision':path.stem, 'validated_response_bytes':len(json.dumps(value['value'],ensure_ascii=False).encode()),
                'output_tokens':usage.get('output_tokens'), 'provider_response_count':usage.get('provider_response_count'),
                'estimated':usage.get('estimated')})
        if usage and not usage.get('estimated', False):
            measured += 1
            for key in totals:
                number = usage.get(key)
                if type(number) in (int, float) and totals[key] is not None:
                    totals[key] += number
                else:
                    totals[key] = None
    return {'version':'mn.litigation.performance.v1', 'stages':stages, 'responses':responses,
        'provider_ledger':{'usage':provider_usage, 'coverage':ledger},
        'recorded_decision_usage':totals if measured else None,
        'reasoning_seconds':None, 'calibration_seconds':None, 'repair_seconds':None,
        'qualification':'Stage duration includes preparation, calibration, transport and repair when performed. Provider reasoning/calibration/repair times are unknown unless separately measured. Not a complete billing ledger.'}
