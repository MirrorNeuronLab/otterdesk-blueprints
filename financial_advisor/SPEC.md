# Financial Advisor Spec

## Goal

Create one financial-advisor blueprint that covers bank statement extraction, tax-form OCR capture, personal financial advice, personal income tax review, and portfolio risk review.

## Inputs

- Local document folder containing statements, receipts, bills, income records, tax forms, tax-form images with answer files, brokerage statements, JSON, CSV, text, or PDFs.
- Optional tax year, filing status, taxpayer profile, portfolio holdings, benchmark weights, risk policy, and market notes.
- Customer purpose, objective, horizon, liquidity, risk tolerance, tax objective, required liquid reserve, other-account coverage, and sale-tax context. Missing fields must remain explicit and block suitability language.

## Logical workflow

`prepare_financial_packet` → `analyze_household_finances` →
`prepare_tax_review` → `analyze_portfolio_risk` →
`collect_public_finance_guidance` → `reconcile_advisor_evidence` →
`publish_financial_review_packet`.

The ordered topology prevents concurrent mutation of regulated financial state.
Within a step, `StepSpec` sequences the bounded specialists. The compiler—not a
domain agent—owns source collection, routing, joins, and logical completion.

## OCR

PDFs and document images use `mirrorneuron-llm-ocr-skill`. Embedded PDF text is preferred when it is substantial; image-only or low-text documents are sent to the shared LightOnOCR-2-1B Docker Model Runner service. The runtime prepares the catalogued OCR model before worker execution; the worker uses the shared endpoint without a Docker CLI. The workflow preserves OCR-required status, extraction method, model metadata, page metadata, and warnings for human review.

## Outputs

- `final_artifact.json`
- `bank_statement_extraction.json`
- `household_finance_summary.json`
- `tax_review_packet.json`
- `tax_form_ocr_capture.json`
- `portfolio_risk_review.json`
- `financial_advisor_report.md`
- `customer_report.json`
- action ledger, artifact quality, and run health records

The JSON workflow bundle remains the audit layer. `customer_report.json` and
`financial_advisor_report.md` are the customer-facing layer: they use
evidence-based statuses, expose missing context, and provide a prioritized
review queue without model/runtime internals.

The customer layer must distinguish missing suitability inputs from stale
market evidence. A completed goals profile does not make fixture-priced
holdings actionable; it changes the evidence gap from “objectives missing” to
“refresh holdings, prices, basis, and account coverage.”

## Persistent job data

Knowledge, Milvus Lite RAG storage, and explicitly durable advisor state are
isolated by stable `job_id` and survive multiple runs. Inputs and outputs are
isolated by `run_id`; ordinary run cleanup never deletes job data.

## Non-Goals

The blueprint does not file taxes, make trades, move money, pay bills, open accounts, or send reports externally. It prepares source-grounded review packets for humans.
