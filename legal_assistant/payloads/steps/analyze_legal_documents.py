from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, parallel, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("prepare_legal_matter")),
    flow=parallel(
        sequence(
            agent("invoice_bill_extractor", as_="invoice_extract"),
            agent("payable_field_validator", as_="payable_validate"),
        ),
        sequence(
            agent("contract_clause_extractor", as_="clause_extract"),
            agent("contract_playbook_comparator", as_="playbook_compare"),
        ),
    ),
    output=OutputSpec(fields={"legal_analysis": flow_output()}),
)
