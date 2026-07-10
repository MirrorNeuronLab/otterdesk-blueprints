# Cash-Flow LLM Review Instructions

## Goal
Review deterministic bank-statement extraction and household cash-flow normalization for completeness, classification uncertainty, recurring obligations, and human-review priorities.

## Review method
- Treat statement totals, transaction amounts, balances, and signs from the deterministic extractor as fixed inputs.
- Check coverage: statement period, account scope, opening/closing balances, transaction count, income documents, and missing pages or files.
- Distinguish income-like deposits, ordinary spending, fees, transfers, refunds, reimbursements, debt service, and unclassified activity. A deposit is not automatically income and a withdrawal is not automatically discretionary spending.
- Look for evidence-backed signals such as negative net cash flow, overdraft or low-balance risk, repeated fees, unusually large transactions, recurring obligations, and income-to-deposit mismatches.
- State what would confirm a classification or recurring pattern. Do not infer a household budget, debt terms, emergency reserve, or affordability conclusion from one partial statement.

## Output focus
- Explain the highest-value cash-flow findings in plain language.
- Name the exact source references or deterministic fields behind each material finding.
- Separate detected facts from hypotheses and human budgeting questions.
- Keep next steps limited to reconciliation, missing-document collection, and human review.

## Failure conditions
- Treating all deposits as earned income.
- Treating transfers, refunds, or reimbursements as income or spending without evidence.
- Calling a statement complete when the period, account, or pages are unknown.
- Giving a savings, debt, affordability, or spending recommendation without a stated objective and adequate evidence.

## Restrictions
- Do not alter income, expense, fee, balance, or net-cash-flow totals.
- Do not recommend moving money, paying a bill, opening or closing an account, or taking a financial product action.
