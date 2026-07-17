from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("legal_document_reader")), flow=agent("contract_clause_extractor"), output=OutputSpec(fields={"clauses": flow_output()}))

