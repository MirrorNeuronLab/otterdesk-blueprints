from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input, upstream

STEP = StepSpec(input=InputSpec(fields={'previous': upstream('capture_mac_evidence', 'result')}), flow=agent('temporal_history_reconciler'),
                output=OutputSpec(fields={'result': flow_output()}))
