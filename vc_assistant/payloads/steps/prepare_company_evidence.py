from mn_sdk.step_graph import (
    InputSpec,
    OutputSpec,
    StepSpec,
    agent,
    flow_output,
    sequence,
)

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("assemble_company_packets", "company_packets")
    ),
    flow=sequence(
        agent("document_evidence_extractor", as_="extract"),
        agent("claim_normalizer", as_="normalize"),
    ),
    output=OutputSpec(fields={"company_evidence": flow_output()}),
)
