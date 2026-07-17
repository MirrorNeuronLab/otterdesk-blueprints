from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("invoice_bill_extractor")), flow=agent("payable_field_validator"), output=OutputSpec(fields={"payables": flow_output()}))

