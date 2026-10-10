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

PDFs and document images use `mirrorneuron-docs-to-markdown-skill`. Embedded PDF text is preferred when it is substantial; image-only or low-text documents are sent to the shared LightOnOCR-2-1B Docker Model Runner service. The runtime prepares the catalogued OCR model before worker execution; the worker uses the shared endpoint without a Docker CLI. The workflow preserves OCR-required status, extraction method, model metadata, page metadata, and warnings for human review.

## Model selection

Actor-style LLM analysis requests the Docker Model Runner proxy's managed
`default` model. Runtime model preparation maps that default to the medium
`nemotron3` catalog model on a qualifying high-memory endpoint, including a
128 GB DGX Spark, and may use the portable small model on less capable
machines. The blueprint does not pin a concrete runtime model or hard-require a
GPU. Live model output is still required during normal runs; deterministic
financial formulas, evidence gates, and review boundaries do not change with
the selected model.

## Outputs

Authoritative reports and audit records live in the SDK-provided run directory,
with run-relative paths recorded in `final_artifact.json`. Configured host
output folders receive additional copies. A specialist publishes its packet
before returning artifact references; the generated step sink retains logical
completion ownership. Later runs must not overwrite prior run reports.

Version 1.0.2 sets the default host output folder to
`~/Downloads/financial-advisor`, matching the declared job name. Previously
submitted jobs retain their configured destination.

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

Knowledge, DuckDB RAG storage, and explicitly durable advisor state are
isolated by stable `job_id` and survive multiple runs. Inputs and outputs are
isolated by `run_id`; ordinary run cleanup never deletes job data.

The top-level Job response service exposes only bounded, non-secret profile,
schedule, lifecycle, and latest-run context. It remains readable without an
active run and cannot file, trade, transfer, configure, or start the job.
Customer-facing review language should lead with the supported answer, state
material uncertainty plainly, and ask one focused follow-up question when
evidence is incomplete.

Version 1.1.3 makes the complete finished customer Markdown report an explicit
conversation subject. The document skill publishes it with conversion receipts
in run-keyed `context_sources/outputs/` under the SDK-provided Job output folder.
Raw documents and JSON audit records remain outside that selection. Publication
must succeed before the report specialist returns; no source is synthesized from
status or a report preview. SDK >=1.3.58.dev86 and its Membrane source-selection
contract preserve complete support groups and explicit omissions. Conversation
does not authorize financial actions or external sharing.

## Non-Goals

The blueprint does not file taxes, make trades, move money, pay bills, open accounts, or send reports externally. It prepares source-grounded review packets for humans.

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.

## Context engine contract

The `mn.context` descriptor explicitly disables Membrane runtime recall for this blueprint: its payload does not call TextMemory. Existing domain knowledge/RAG, live status, MCP controls, and Core coordination retain their own contracts. The retired conversation-memory declaration is removed, so this workflow does not start a context compressor or require a Membrane SDK merely to launch. Any future runtime-memory consumer must declare `mirrorneuron-python-sdk[context]`, ingest complete preprocessed text under trusted job/run scope, and use the Markdown/DuckDB CPU service.

## Shared capability ownership

Document intake, OCR record normalization, lazy client configuration, and model diagnostics belong to the shared docs-to-markdown skill. Version 1.1.1 replaces the retired document-reading and LLM OCR distributions with this package; local source preparation stages it from `mn-skills/docs_to_markdown_skill`. Financial classification, review-only policy and report composition remain blueprint-owned.
