from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("tax_form_ocr_capturer")), flow=agent("tax_workpaper_preparer"), output=OutputSpec(fields={"tax_workpapers": flow_output()}))

