from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("prepare_financial_packet")),
    flow=sequence(
        agent("bank_statement_extractor", as_="statements"),
        agent("cash_flow_normalizer", as_="normalize"),
        agent("cash_flow_llm_analyst", as_="review"),
    ),
    output=OutputSpec(fields={"household_finance_analysis": flow_output()}),
)
