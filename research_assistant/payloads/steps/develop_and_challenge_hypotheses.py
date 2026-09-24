from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields={
        **inputs(),
        "evidence_coverage": upstream("assess_evidence_coverage", "evidence_coverage"),
        "experiment_readiness": upstream("assess_experiment_readiness", "experiment_readiness"),
    }),
    flow=agent("autonomous_researcher"),
    output=OutputSpec(fields={"hypothesis_analysis": flow_output()}),
)
