from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("financial_folder_watcher")), flow=agent("financial_document_reader"), output=OutputSpec(fields={"document_inventory": flow_output()}))

