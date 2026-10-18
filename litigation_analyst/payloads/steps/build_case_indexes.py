from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input, upstream

STEP = StepSpec(
    input=InputSpec(fields={'input_folder': run_input('input_folder'), 'matter_file': run_input('matter_file'), 'goal': run_input('goal'), 'output_folder': run_input('output_folder'), 'previous': upstream('prepare_case_sources')}),
    flow=agent('case_index_builder'),
    output=OutputSpec(fields={"result": flow_output()}),
)
