from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("prepare_tax_review")),
    flow=sequence(
        agent("portfolio_context_loader", as_="holdings"),
        agent("portfolio_market_data_loader", as_="market_data"),
        agent("portfolio_risk_engine", as_="risk"),
        agent("portfolio_llm_reviewer", as_="review"),
    ),
    output=OutputSpec(fields={"portfolio_risk_analysis": flow_output()}),
)
