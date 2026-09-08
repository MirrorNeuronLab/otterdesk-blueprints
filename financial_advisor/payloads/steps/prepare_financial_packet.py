from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs()),
    flow=sequence(
        agent("financial_folder_watcher", as_="inventory"),
        agent("financial_document_reader", as_="extract"),
    ),
    output=OutputSpec(fields={"financial_packet": flow_output()}),
)
