from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("frame_purchase_request")),
    flow=agent("purchase_knowledge_retriever"),
    output=OutputSpec(fields={"purchase_evidence": flow_output()}),
)
