from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream

STEP = StepSpec(input=InputSpec(fields={'previous': upstream('capture_software_sources', 'result')}), flow=agent('software_rule_author'),
                output=OutputSpec(fields={'result': flow_output()}))
