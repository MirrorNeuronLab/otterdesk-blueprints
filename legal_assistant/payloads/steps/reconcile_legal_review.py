from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("analyze_legal_documents")),
    flow=sequence(
        agent("legal_evidence_reconciler", as_="reconcile"),
        agent("legal_review_auditor", as_="audit"),
    ),
    output=OutputSpec(fields={"reconciled_review": flow_output()}),
)
