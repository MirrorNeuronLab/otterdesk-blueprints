from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("collect_public_finance_guidance")),
    flow=sequence(
        agent("advisor_evidence_reconciler", as_="reconcile"),
        agent("advisor_review_auditor", as_="audit"),
    ),
    output=OutputSpec(fields={"advisor_review": flow_output()}),
)
