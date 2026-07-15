from mn_sdk.step_graph import (
    InputSpec,
    OutputSpec,
    StepSpec,
    agent,
    flow_output,
    parallel,
)

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(fields=step_inputs("plan_public_research", "research_plan")),
    flow=parallel(
        agent("company_identity_researcher"),
        agent("funding_researcher"),
        agent("market_comp_researcher"),
        agent("traction_verifier"),
        agent("rendered_page_researcher"),
    ),
    output=OutputSpec(fields={"public_research": flow_output()}),
)
