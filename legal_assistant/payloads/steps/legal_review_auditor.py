from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("legal_evidence_reconciler")), flow=agent("legal_review_auditor"), output=OutputSpec(fields={"audit": flow_output()}))

