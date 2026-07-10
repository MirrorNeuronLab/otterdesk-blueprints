# Financial Advisor Spec

## Goal

Create one financial-advisor blueprint that covers bank statement extraction, tax-form OCR capture, personal financial advice, personal income tax review, and portfolio risk review.

## Inputs

- Local document folder containing statements, receipts, bills, income records, tax forms, tax-form images with answer files, brokerage statements, JSON, CSV, text, or PDFs.
- Optional tax year, filing status, taxpayer profile, portfolio holdings, benchmark weights, risk policy, and market notes.

## OCR

PDFs and document images use `mirrorneuron-llm-ocr-skill`. Embedded PDF text is preferred when it is substantial; image-only or low-text documents are sent to the shared LightOnOCR-2-1B Docker Model Runner service. The OCR skill lazily pulls and starts the compatible model on first required use, and the workflow preserves OCR-required status, extraction method, model metadata, page metadata, and warnings for human review.

## Outputs

- `final_artifact.json`
- `bank_statement_extraction.json`
- `household_finance_summary.json`
- `tax_review_packet.json`
- `tax_form_ocr_capture.json`
- `portfolio_risk_review.json`
- `financial_advisor_report.md`
- action ledger, artifact quality, and run health records

## Non-Goals

The blueprint does not file taxes, make trades, move money, pay bills, open accounts, or send reports externally. It prepares source-grounded review packets for humans.
