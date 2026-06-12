# OtterDesk Blueprints

`otterdesk-blueprints` is a self-contained OtterDesk-facing worker blueprint catalog. Each blueprint folder includes
its own manifest, configuration, payloads, README, and user-facing `SPEC.md`.

## Quick Start

List available blueprints:

```bash
mn blueprint list
```

Run a catalog blueprint:

```bash
mn run <blueprint_id>
```

Run a checked-in folder directly:

```bash
cd <blueprint_id>
mn run --folder .
```

Run repository tests:

```bash
.venv/bin/python -m pytest -q
```

## Catalog

| Blueprint | Category | Purpose |
| --- | --- | --- |
| [`drug_discovery_research_assistant`](drug_discovery_research_assistant/README.md) | Science | Helps run a reviewable discovery workflow that proposes, filters, and evaluates drug candidates across repeated research stages. |
| [`generic_customer_service_voice_coworker`](generic_customer_service_voice_coworker/README.md) | Business | Runs a localhost-proxied Spark HTTPS/WebRTC pizza-ordering voice co-worker with editable menu knowledge and NVIDIA ASR, Nemotron vLLM, and Magpie TTS. |
| [`personal_income_tax_expert`](personal_income_tax_expert/README.md) | Finance | Runs an LLM-assisted tax preparation team over local tax documents, builds draft Form 1040 workpapers, audits the packet, and writes JSON, Markdown, and PDF review outputs. |
| [`portfolio_risk_review_assistant`](portfolio_risk_review_assistant/README.md) | Finance | Stress-tests a portfolio against market crashes, rate shocks, and liquidity pressure, then explains risks and possible rebalancing options in plain language. |
| [`property_deal_research_assistant`](property_deal_research_assistant/README.md) | Finance | Reviews ZIP-code history, broker notes, financing constraints, and deal memory to rank property opportunities and explain which ones deserve attention. |
| [`video_watch_assistant`](video_watch_assistant/README.md) | Security | Watches an approved video stream, detects configured visual targets, and reports count, label, category, color, position, activity, and alert status for review. |
| [`invoice_bill_extraction_assistant`](invoice_bill_extraction_assistant/README.md) | Finance | Extracts invoice, bill, supplier, tax, total, line item, consumption, and approval-routing fields from local invoice PDFs with shared LLM OCR fallback. |
| [`legal_contract_clause_review_assistant`](legal_contract_clause_review_assistant/README.md) | Legal | Reviews local contract PDFs, extracts important clauses, compares them with a playbook, and writes a source-grounded legal review packet. |
| [`medical_deid_record_intake_assistant`](medical_deid_record_intake_assistant/README.md) | Healthcare | Detects and redacts PHI or PII from clinical-style PDFs, extracts patient-record intake fields, and writes a review-gated de-identification packet. |
| [`tax_form_ocr_capture_assistant`](tax_form_ocr_capture_assistant/README.md) | Finance | Classifies tax forms, locates fields, captures structured taxpayer and line-item values, validates totals, and writes a review-only tax intake packet. |
| [`bank_statement_extraction_assistant`](bank_statement_extraction_assistant/README.md) | Finance | Extracts bank statement account metadata, balances, transaction rows, debits, credits, fees, and validation checks from local statement PDFs. |

## Folder Contract

Most blueprint folders contain:

| Path | Purpose |
| --- | --- |
| `README.md` | Self-contained quickstart, inspection notes, and validation guidance. |
| `SPEC.md` | User-facing problem, outcome, evaluation criteria, limits, and upgrade path. |
| `TERM.md` | Terms, assumptions, or domain notes when present. |
| `manifest.json` | Workflow contract, workflow steps and transitions, agent communication graph, runtime worker bindings, metadata, runners, services, and environment access. |
| `config/default.json` | Default launch configuration and mock/sample inputs. |
| `config/overwrite.json` | Optional local overrides. Do not commit customer secrets. |
| `payloads/` | Worker code, prompts, policies, fixtures, and support files. |

## Safety Checklist

- Review `manifest.json`, `payloads/`, and `pass_env` before live runs.
- Start with mock, dry-run, or quick-test settings before enabling real external services.
- Keep customer-specific inputs and secrets in local overrides or environment variables.
- Update the local blueprint README and `SPEC.md` when behavior, inputs, outputs, or limits change.
