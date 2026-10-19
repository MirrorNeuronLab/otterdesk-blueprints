from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream

STEP = StepSpec(input=InputSpec(fields={}), flow=agent('software_source_curator'),
                output=OutputSpec(fields={'result': flow_output()}))
