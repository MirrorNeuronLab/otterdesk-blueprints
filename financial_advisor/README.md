# Financial Advisor

The generated `financial_advisor_report.md` and `customer_report.json` are
customer-facing and prioritize evidence status, missing context, and a ranked
action queue. The full JSON bundle remains the audit layer.

Reports and audit records are published in the SDK-provided run directory.
The final artifact records run-relative output paths so OtterDesk can discover
them on either node. The configured output folder receives additional copies;
later runs retain earlier run reports. Report publication does not complete
the logical workflow; the generated step sink owns completion.

`financial_advisor` is a unified review-only finance blueprint. Put bank statements, receipts, bills, income records, W-2s, 1099s, tax-form images with answer files, brokerage statements, portfolio files, and related finance documents in the input folder. It extracts bank-statement evidence, captures tax-form OCR fields for review, normalizes household cash flow, prepares draft tax workpapers, reviews portfolio risk, and writes an integrated advisor packet to the output folder.

## Run

From the repository root:

```bash
mn blueprint run ./financial_advisor
```

Skill versions are declared in `dependencies.json`. In local dev mode, the
runtime loads these skills from the local source folders. In binary production,
the same declarations select versioned GAR/pip packages.

Or from this blueprint folder:

```bash
mn blueprint run .
```

The default sample input folder is `financial_advisor/examples/sample_inputs`; the default output folder is `~/Downloads/financial-advisor`. The sample folder includes synthetic bank/tax/portfolio text fixtures plus tax-form image/label pairs for local OCR-capture validation.

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

PDFs and document images use the shared `mirrorneuron-docs-to-markdown-skill`. Embedded PDF text is used when it is substantial; image-only or low-text PDFs, PNGs, JPGs, TIFFs, BMPs, and WEBPs are sent to LightOnOCR-2-1B through Docker Model Runner. The runtime prepares and starts the shared OCR model before the worker begins; the worker uses the shared endpoint and never needs a Docker CLI. The workflow records the extraction method, OCR model, warnings, and review-required status in the output packet. Explicit fake/quick-test runs skip model startup.

## Shared job data

Each configured advisor job owns persistent `knowledge/`, `databases/rag/`,
and `state/`. Bundled knowledge seeds once; later runs preserve edits. Customer
documents and reports remain run-scoped unless explicitly written as durable
state.

## Safety

Outputs are review-only. The blueprint does not file tax returns, make trades, move money, pay bills, open accounts, or share regulated financial data. Human approval is required before any downstream action.

## Model Profiles

Normal runs request the Docker Model Runner proxy's managed `default` model.
Version 1.1.5 uses an 8,192-token context, a 1,800-token response limit,
a 300-second request deadline, and two retries with a one-second backoff.
The deadline includes gateway queueing and generation; local reviews can
take longer than the previous 60-second limit even when the model is healthy.
Override `llm.configs.primary.timeout_seconds` to tune the deadline per run.
The context is declared explicitly so advisor
reviews do not request the model catalog's larger default allocation.
Financial Advisor retains strict JSON validation and requires live responses.
The runtime selects and prepares the medium `nemotron3` catalog model when a
capable endpoint is advertised, including a DGX Spark with 128 GB of unified
memory. On smaller machines, the catalog may select the portable small model.
The blueprint does not pin a concrete runtime model or impose a hard GPU
requirement, but normal runs still require live model responses and fail rather
than silently accepting deterministic fallback advice. Explicit fake/quick-test
runs do not need a live model.

## Payload layout

`payloads/steps/` contains logical contracts and collaboration graphs.
The 17 stock SDK block workers call their owning domain functions directly.
Focused modules retain intake, cash flow, tax, portfolio, reconciliation,
reporting and model-review policy. No blueprint runtime or compatibility adapter
is used; offline samples exercise compiled worker bindings, and Core owns
production run completion.

## Persistent conversation

OtterDesk can ask this hired co-worker about its role, schedule, evidence gaps,
and latest review through the stable Job response service even before its first
run or while it is idle. Conversation never starts a financial review.
The conversation should answer in plain language, distinguish observed findings
from missing evidence, and suggest one focused follow-up question when context is
incomplete. The workflow reviewers use the same source-grounded conversation
guidance when preparing customer-facing findings.

Version 1.1.3 publishes the complete finished `financial_advisor_report.md`
through the document-conversion skill into run-keyed
`context_sources/outputs/` under the SDK-provided Job output folder. Conversion
receipts retain original and Markdown hashes; retries reuse unchanged reports
and later runs retain earlier reports. The runtime responder uses Membrane source
intelligence for these report questions. Raw financial inputs and JSON audit
records are excluded. SDK >=1.3.58.dev86 is required for bounded whole-section
selection; review and downstream approval requirements remain unchanged.

## Block composition (4.0.1)

All 17 specialist bindings reference their owning native domain functions. The seven ordered logical steps and their StepSpec specialist sequences remain intact. Intake commits the approved source bytes; every specialist consumes a verified immutable evidence packet. Model reviews use the common block capability journal for dispatch and replay, alongside SDK budgets, backpressure and diagnostics. Version 4.0.1 saves an observed response and its token usage before checking cancellation or publishing domain artifacts, so those interruptions recover without repeating model work. Observed live-model failures replay their original diagnostic; only a genuinely interrupted call without an observed outcome requires reconciliation. Normal runs continue to require live responses and never substitute fallback financial advice. SDK publication commits the customer report and audit bundle, then the document skill prepares the complete saved Markdown as the conversation subject. Publication requires a completed audit and preserves review-only financial policy; Core owns scheduling and logical completion.

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

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

## Conversation continuity and saved review instructions

OtterDesk keeps the current review topic, confirmed setup answers and pending
question with this hired co-worker. Keep short follow-ups on that topic and ask
one focused question when a reference is ambiguous. Surface useful findings,
actual decisions and completion; routine extraction activity stays in status.
When discussing a saved review, lead with the supported finding, its period and
source freshness, the uncertainty and the next useful question for an advisor.

Chat > Memory stores only explicit supervisor preferences and working rules.
The optional `inputs.payload.supervisor_instructions` list defaults to `[]`.
Intake validates at most 50 items, 1,000 characters per item and 16,000 UTF-8 JSON
bytes, captures its revision with the financial evidence packet, and passes the
snapshot to financial review prompts. Rules can guide review emphasis and
explanation; they cannot change amounts, calculations, screening formulas,
source facts or required review blockers. Changes and forgetting affect future
runs; historical records keep their original snapshot.

OtterDesk reads `payloads/prompts/conversation.json` for stage guidance. Existing
Membrane source intelligence remains the authority for prepared financial report
questions. Raw financial inputs, audit JSON, ordinary conversation and saved
preferences are not additional financial evidence. Filing, trading, payments,
transfers, account opening and external sharing remain outside this role.
