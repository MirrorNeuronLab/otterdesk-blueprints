from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream

STEP = StepSpec(input=InputSpec(fields={'previous': upstream('verify_software_rules', 'result')}), flow=agent('software_rules_reporter'),
                output=OutputSpec(fields={'result': flow_output()}))
