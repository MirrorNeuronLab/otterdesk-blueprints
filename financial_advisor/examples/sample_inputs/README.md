# Financial Advisor Sample Inputs

This folder contains synthetic fixtures for the unified `financial_advisor` blueprint.

- `community_bank_statement.txt` exercises bank statement extraction and cash-flow normalization.
- `sample-w2.txt`, `sample-1099-int.txt`, and `sample-1099-r-401k.txt` exercise draft tax workpaper routing.
- `sample_portfolio.json` exercises portfolio risk review.
- The default config supplies a synthetic customer goal/risk profile so the
  workflow can distinguish risk-metric review from suitability gaps. It still
  records that an employer plan and brokerage tax lots are outside the packet.

The sample intentionally contains only one bank-statement period, fixture
portfolio prices, and tax-form images with sparse labels. A credible output
should therefore surface limited cash-flow coverage, tax capture gaps, stale
market-data risk, and the need to verify tax lots before any allocation change.

The files are not real customer data and are intended only for local blueprint validation.
