from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("advisor_review_auditor")), flow=agent("financial_advice_reporter"), output=OutputSpec(fields={"financial_report": flow_output()}))

