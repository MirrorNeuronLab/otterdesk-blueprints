from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("public_finance_researcher")), flow=agent("advisor_evidence_reconciler"), output=OutputSpec(fields={"reconciled_evidence": flow_output()}))

