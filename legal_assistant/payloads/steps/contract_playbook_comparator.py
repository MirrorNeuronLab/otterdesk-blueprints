from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("contract_clause_extractor")), flow=agent("contract_playbook_comparator"), output=OutputSpec(fields={"playbook_comparison": flow_output()}))

