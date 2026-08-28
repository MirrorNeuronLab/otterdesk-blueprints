from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(
        fields=inputs("compare_purchase_options", "option_comparison")
    ),
    flow=agent("purchase_recommendation_auditor"),
    output=OutputSpec(fields={"audited_recommendation": flow_output()}),
)
