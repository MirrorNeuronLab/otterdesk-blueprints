# Portfolio Risk Review Playbook

Use this guidance as local retrieval context for review-only portfolio risk analysis.

## Evidence Grounding

- Separate user holdings, public market data, risk policy, scenario assumptions, Monte Carlo results, and LLM-written commentary.
- Treat public quotes and history as required market inputs with freshness checks.
- Preserve source refs for market data and deterministic calculations.

## Review Checks

- Flag stale prices, insufficient return history, concentration, liquidity, turnover, cash, VaR, CVaR, drawdown, and benchmark-policy gaps.
- Explain ranked actions as review candidates, not trading instructions.
- Keep deterministic risk math authoritative over narrative LLM summaries.

## Tool Boundaries

- Market data loading, risk engines, simulations, and benchmark evaluators are tools for review.
- If required market data fails, fail closed rather than producing a report from invented prices.
