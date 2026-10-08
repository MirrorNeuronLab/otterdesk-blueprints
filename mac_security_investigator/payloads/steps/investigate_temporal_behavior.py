from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input, upstream

STEP = StepSpec(input=InputSpec(fields={'previous': upstream('reconcile_evidence_history', 'result')}), flow=agent('temporal_behavior_investigator'),
                output=OutputSpec(fields={'result': flow_output()}))
