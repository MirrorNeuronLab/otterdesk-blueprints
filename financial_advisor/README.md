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

## Process and agents

The compiled workflow uses seven ordered logical steps because all financial
lanes contribute to one regulated durable state packet:

1. `prepare_financial_packet`: inventory and read sources.
2. `analyze_household_finances`: extract the statement, normalize cash flow, and review it.
3. `prepare_tax_review`: route tax sources, capture form fields, prepare workpapers, and audit tax evidence.
4. `analyze_portfolio_risk`: load holdings and customer context, attach fixture/current market evidence, compute risk, and review suitability gaps.
5. `collect_public_finance_guidance`: record bounded public guidance sources.
6. `reconcile_advisor_evidence`: reconcile every lane and audit the integrated packet.
7. `publish_financial_review_packet`: durably write the customer and audit layers.

These steps invoke 17 same-named specialists. Agent outputs are bounded and
route-neutral; the runtime-generated source/sink controls own logical step
completion.

The sample is intentionally close to a household review: it yields one month of
cash flow with a transaction still needing classification, draft income from
W-2/1099 sources, incomplete Schedule E capture, a three-holding portfolio, a
complete goals profile, stale fixture-price warnings, and a ranked customer
action queue.

## PDF and Image OCR

PDFs and document images use the shared `mirrorneuron-llm-ocr-skill`. Embedded PDF text is used when it is substantial; image-only or low-text PDFs, PNGs, JPGs, TIFFs, BMPs, and WEBPs are sent to LightOnOCR-2-1B through Docker Model Runner. The runtime prepares and starts the shared OCR model before the worker begins; the worker uses the shared endpoint and never needs a Docker CLI. The workflow records the extraction method, OCR model, warnings, and review-required status in the output packet. Explicit fake/quick-test runs skip model startup.

## Shared job data

Each configured advisor job owns persistent `knowledge/`, `databases/rag/`,
and `state/`. Bundled knowledge seeds once; later runs preserve edits. Customer
documents and reports remain run-scoped unless explicitly written as durable
state.

## Safety

Outputs are review-only. The blueprint does not file tax returns, make trades, move money, pay bills, open accounts, or share regulated financial data. Human approval is required before any downstream action.

## Model Profiles

The small default profile uses `small`. Heavy review/reporting nodes can use the `large` profile backed by `medium`, following the `vc_assistant` pattern.

## Payload layout

`payloads/steps/` contains only logical contracts and collaboration graphs.
`payloads/agents/` binds each specialist. `payloads/domain/` is split into
intake, source ingestion, cash flow, tax, portfolio, public research,
reconciliation, reporting, model-review services, durable state, and runtime
preparation. `composition.py` is the local sample runner; deployed agents call
the same focused functions.
