from mn_sdk.blueprint.steps import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("calculate_valuation_scores", "valuation_scores")
    ),
    flow=agent("score_consistency_auditor"),
    output=OutputSpec(fields={"audited_analysis": flow_output()}),
)
