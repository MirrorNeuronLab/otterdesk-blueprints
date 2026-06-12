# Personal Financial Advisor Specification

## Purpose

Individuals, households, freelancers, and financial coaches need a private continuous service coworker that can monitor incoming finance documents, summarize cash-flow status, identify missing or risky items, research public guidance, and prepare review-only advice without moving money or sharing private document data.

## Public Dataset Input

The blueprint is seeded with `AgamiAI Indian Bank Statement Synthetic Dataset` as a public finance-document sample source.

- URL: https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements
- Alternate URL: n/a
- Provider: AgamiAI on Hugging Face
- License note: Apache 2.0
- Download note: Use the bundled sample files or fetch a small public sample before trying a larger local folder.

## OCR Skill

The workflow uses `mn-skills/llm_ocr_skill` via `extract_document_folder(...)` and the Docker Model Runner LightOnOCR configuration. Embedded text is preferred; scanned PDFs and document images are routed through OCR only when needed. Downstream evidence preserves `ocr_required`, `extraction_method`, warnings, page metadata, and model metadata.

## Browser Research Skill

The workflow uses `mn-skills/w3m_browser_skill` only inside the `financial_market_researcher` DockerWorker image. The skill shells out to `w3m -dump` for public web pages and returns compact source notes. It does not start Docker, manage sidecars, or browse with a GUI.

Research queries are generated only from generic risk categories and document types. The advisor must not send raw customer document text, account numbers, taxpayer IDs, names, transaction descriptions, or other regulated identifiers to public web services.

Research context requests set `use_model_compression=true` for Membrane. Operators must also run Membrane with `MN_CONTEXT_MODEL_COMPRESSION_ENABLED=true` and Docker Model Runner model `hf.co/homerquan/mn-context-engine-model-v-Q4_K_M` for model compression to activate.

## Fields

- `document_kind`
- `institution_or_merchant`
- `account_or_source`
- `document_date`
- `income_amounts`
- `expense_amounts`
- `recurring_items`
- `balances`
- `debt_or_credit_obligations`
- `fees`
- `risk_flags`
- `recommended_actions`
- `research_summary`
- `research_sources`
- `research_warnings`

## Workflow

- Financial Folder Watcher: Resolve the monitored folder, output folder, monitoring settings, and sample input notes.
- Financial Document Reader: Read embedded text and call shared `llm_ocr_skill` for scanned or low-text statements, receipts, bills, income documents, and images.
- Financial Activity Classifier: Classify income, expenses, balances, bills, fees, debt obligations, and source document types.
- Financial Health Assessor: Estimate cash-flow status, identify document gaps, reminders, anomalies, and review-only risk flags.
- Financial Market Researcher: Use `w3m_browser_skill` to gather privacy-safe public guidance for detected review categories.
- Financial Advice Reporter: Write a review-only personal financial advisor report with status, advice, reminders, risks, and source evidence.

## Output Contract

The final artifact contains the standard OtterDesk fields plus personal finance review sections:

- `type`: `personal_financial_advisor_report`
- `executive_summary`
- `recommended_action`: `review_household_finance_report_before_any_financial_action`
- `confidence`
- `evidence`
- `next_steps`
- `source_refs`
- `status`
- `advisor_message`
- `document_summary`
- `financial_snapshot`
- `income_summary`
- `expense_summary`
- `risk_register`
- `advisor_recommendations`
- `reminders`
- `research_summary`
- `research_sources`
- `research_warnings`
- `watch_state`
- `output_files`

## Monitoring

Continuous folder polling is the default service behavior. Polling uses `monitoring.poll_interval_seconds`, records processed file fingerprints, and supports `monitoring.max_cycles` for bounded tests or smoke runs. A one-shot scan is available only through an explicit override such as CLI `--once` or `monitoring.enabled=false`.

## Mixed Runtime

The default worker runner is `MirrorNeuron.Runner.HostLocal`. The folder watch, extraction, classification, assessment, and report-writing agents use the HostLocal `scripts/run_blueprint.py` phase worker shape.

Only `financial_market_researcher` uses `MirrorNeuron.Runner.DockerWorker` with the payload-local image build source `document_workflow/docker_worker` and command `bash scripts/run_blueprint_in_docker_worker.sh`. The blueprint must not declare a browser sidecar, publish host ports, or require HostLocal phases to import `w3m_browser_skill`.

## Safety Rules

- All extracted values, reminders, risk flags, and recommendations are review-only.
- Human approval is required before external sharing or consequential financial use.
- The blueprint must not move money, pay bills, place trades, file taxes, sync accounting systems, or mark advice final.
- Browser research is public-context enrichment only and must not leak private document text or identifiers.
- Logs and events must redact regulated and confidential identifiers.
- Dataset licenses and terms remain the operator's responsibility.
