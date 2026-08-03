from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("contacts_csv")),
    flow=agent("bibblio_growth_lead"),
    output=OutputSpec(fields={"qualified_seed_contacts": flow_output()}),
)

