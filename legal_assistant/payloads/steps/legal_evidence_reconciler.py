from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("contract_playbook_comparator")), flow=agent("legal_evidence_reconciler"), output=OutputSpec(fields={"issues": flow_output()}))

