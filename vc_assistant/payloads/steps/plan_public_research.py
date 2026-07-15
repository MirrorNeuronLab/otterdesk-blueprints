from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("prepare_company_evidence", "company_evidence")
    ),
    flow=agent("research_planner"),
    output=OutputSpec(fields={"research_plan": flow_output()}),
)
