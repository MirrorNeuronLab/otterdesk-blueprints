from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs()), flow=agent("financial_folder_watcher"), output=OutputSpec(fields={"folder_inventory": flow_output()}))

