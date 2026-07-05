# Financial Advisor Spec

## Goal

Create one financial-advisor blueprint that covers bank statement extraction, personal financial advice, personal income tax review, and portfolio risk review.

## Inputs

- Local document folder containing statements, receipts, bills, income records, tax forms, brokerage statements, JSON, CSV, text, or PDFs.
- Optional tax year, filing status, taxpayer profile, portfolio holdings, benchmark weights, risk policy, and market notes.

## Outputs

- `final_artifact.json`
- `bank_statement_extraction.json`
- `household_finance_summary.json`
- `tax_review_packet.json`
- `portfolio_risk_review.json`
- `financial_advisor_report.md`
- action ledger, artifact quality, and run health records

## Non-Goals

The blueprint does not file taxes, make trades, move money, pay bills, open accounts, or send reports externally. It prepares source-grounded review packets for humans.
