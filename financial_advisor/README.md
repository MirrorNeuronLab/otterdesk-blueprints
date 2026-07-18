# Financial Advisor

The generated `financial_advisor_report.md` and `customer_report.json` are
customer-facing and prioritize evidence status, missing context, and a ranked
action queue. The full JSON bundle remains the audit layer.

`financial_advisor` is a unified review-only finance blueprint. Put bank statements, receipts, bills, income records, W-2s, 1099s, tax-form images with answer files, brokerage statements, portfolio files, and related finance documents in the input folder. It extracts bank-statement evidence, captures tax-form OCR fields for review, normalizes household cash flow, prepares draft tax workpapers, reviews portfolio risk, and writes an integrated advisor packet to the output folder.

## Run

```bash
mn run financial_advisor
```

Or from the folder:

```bash
cd financial_advisor
mn run --folder .
```

The default sample input folder is `financial_advisor/examples/sample_inputs`; the default output folder is `~/Downloads/financial_advisor`. The sample folder includes synthetic bank/tax/portfolio text fixtures plus tax-form image/label pairs for local OCR-capture validation.

## PDF and Image OCR

PDFs and document images use the shared `mirrorneuron-llm-ocr-skill`. Embedded PDF text is used when it is substantial; image-only or low-text PDFs, PNGs, JPGs, TIFFs, BMPs, and WEBPs trigger the skill's private OCR model. The skill passes its model specification to the SDK wrapper, which installs or reuses it on the best compatible cluster node on first OCR use. The blueprint does not declare or preload that model, and the worker never needs a Docker CLI. The workflow records the extraction method, OCR model, warnings, and review-required status in the output packet. Explicit fake/quick-test runs skip OCR.

## Safety

Outputs are review-only. The blueprint does not file tax returns, make trades, move money, pay bills, open accounts, or share regulated financial data. Human approval is required before any downstream action.

## Model Profiles

The small default profile uses `small`. Heavy review/reporting nodes can use the `large` profile backed by `medium`, following the `vc_assistant` pattern.
