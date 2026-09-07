from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input, upstream

STEP = StepSpec(
    input=InputSpec(fields={'input_folder': run_input('input_folder'), 'goal': run_input('goal'), 'output_folder': run_input('output_folder'), 'previous': upstream('investigate_case_evidence')}),
    flow=agent('litigation_draft_editor'),
    output=OutputSpec(fields={"result": flow_output()}),
)
