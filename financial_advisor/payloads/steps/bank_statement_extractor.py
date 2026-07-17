from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("financial_document_reader")), flow=agent("bank_statement_extractor"), output=OutputSpec(fields={"statement_evidence": flow_output()}))

