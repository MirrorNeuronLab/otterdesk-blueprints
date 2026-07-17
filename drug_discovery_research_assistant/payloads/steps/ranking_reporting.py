from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("binding_evaluation")), flow=agent("ranking_reporting"), output=OutputSpec(fields={"discovery_report": flow_output()}))

