from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("analyze_household_finances")),
    flow=sequence(
        agent("tax_document_router", as_="route"),
        agent("tax_form_ocr_capturer", as_="capture"),
        agent("tax_workpaper_preparer", as_="workpapers"),
        agent("tax_llm_reviewer", as_="review"),
    ),
    output=OutputSpec(fields={"tax_review": flow_output()}),
)
