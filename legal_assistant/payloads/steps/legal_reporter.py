from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("legal_review_auditor")), flow=agent("legal_reporter"), output=OutputSpec(fields={"legal_report": flow_output()}))

