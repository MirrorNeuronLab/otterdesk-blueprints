from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input, upstream

STEP = StepSpec(input=InputSpec(fields={'previous': upstream('investigate_temporal_behavior', 'result')}), flow=agent('security_evidence_reporter'),
                output=OutputSpec(fields={'result': flow_output()}))
