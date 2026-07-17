from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("collect_purchase_context")), flow=agent("retrieve_purchase_knowledge"), output=OutputSpec(fields={"knowledge_context": flow_output()}))

