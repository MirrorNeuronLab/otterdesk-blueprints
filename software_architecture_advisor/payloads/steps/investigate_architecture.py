from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input, upstream

STEP = StepSpec(
    input=InputSpec(fields={'repository_url': run_input('repository_url'), 'input_folder': run_input('input_folder'), 'goal': run_input('goal'), 'graph_export': run_input('graph_export'), 'output_folder': run_input('output_folder'), 'previous': upstream('capture_repository')}),
    flow=agent('architecture_investigator'),
    output=OutputSpec(fields={"result": flow_output()}),
)
