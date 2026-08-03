from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(
        fields=inputs(
            "contacts_csv",
            "email_send_approval",
            previous_step="publish_gtm_outreach_queue",
        )
    ),
    flow=agent("growth_partnerships_lead"),
    output=OutputSpec(fields={"email_delivery_result": flow_output()}),
)
