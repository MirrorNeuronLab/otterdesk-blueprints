from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("contacts_csv", previous_step="qualify_seed_contacts")),
    flow=agent("growth_partnerships_lead"),
    output=OutputSpec(fields={"gtm_outreach_packet": flow_output()}),
)

