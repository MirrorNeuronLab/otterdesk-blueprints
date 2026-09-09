from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("collect_public_research", "public_research")
    ),
    flow=agent("research_reconciler"),
    output=OutputSpec(fields={"reconciled_evidence": flow_output()}),
)
