# Portfolio Risk Retrieval Playbook

## Useful Retrieval Queries

- Which holdings, weights, benchmark targets, and policy limits were supplied by the user?
- Where are concentration, liquidity, duration, tax, or drawdown risks outside the stated policy?
- Which recommendation is supported by deterministic simulation output rather than market opinion?

## Evidence Checklist

Use supplied portfolio values, market signals, benchmark allocations, and risk policy as primary evidence. Never invent prices, returns, correlations, tax lots, or expected alpha. If a required value is missing, return a blocker or a low-confidence assumption instead of filling the gap.

Compare single-name weights, sector weights, cash-equivalent coverage, fixed-income duration exposure, and benchmark drift. Separate "mathematical risk" from "advice": the assistant may propose review-only actions such as rebalance with new cash, reduce concentration, request missing tax lots, or stress test drawdown assumptions.

## Output Guidance

The final review should include risk score, strongest risk drivers, benchmark comparison, policy exceptions, evidence references, and a human-review action list. Use cautious language for investment suitability and avoid executable trade instructions unless the user has supplied an approved policy and still mark them review-only.
