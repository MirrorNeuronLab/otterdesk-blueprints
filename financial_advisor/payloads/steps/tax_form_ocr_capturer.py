from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("tax_document_router")), flow=agent("tax_form_ocr_capturer"), output=OutputSpec(fields={"tax_ocr": flow_output()}))

