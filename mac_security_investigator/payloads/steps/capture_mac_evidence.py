from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

STEP = StepSpec(input=InputSpec(fields={}), flow=agent('mac_evidence_collector'),
                output=OutputSpec(fields={'result': flow_output()}))
