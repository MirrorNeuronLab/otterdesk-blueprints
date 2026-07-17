from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("advisor_evidence_reconciler")), flow=agent("advisor_review_auditor"), output=OutputSpec(fields={"audit": flow_output()}))

