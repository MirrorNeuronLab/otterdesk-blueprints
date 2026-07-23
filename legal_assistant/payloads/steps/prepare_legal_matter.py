from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs()),
    flow=sequence(
        agent("legal_folder_watcher", as_="inventory"),
        agent("legal_document_reader", as_="extract"),
    ),
    output=OutputSpec(fields={"matter_evidence": flow_output()}),
)
