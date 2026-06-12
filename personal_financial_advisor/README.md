# Personal Financial Advisor

`Blueprint ID:` `personal_financial_advisor`
`Category:` `Finance`

Continuously monitors a local personal finance folder, OCRs statements, income documents, receipts, bills, and related records, researches public financial guidance with `w3m_browser_skill`, then writes review-only household finance status, advice, risk reminders, and source-grounded reports.

## Public Sample Input

- Dataset: AgamiAI Indian Bank Statement Synthetic Dataset
- Source: https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements
- Expected files: PDF, image, TXT, JSON, and CSV finance documents
- Note: The bundled public sample is a synthetic bank statement subset. Real runs can include income records, bank statements, receipts, bills, credit-card statements, loan records, and similar local finance files.

## What It Does

This OtterDesk blueprint runs as a continuous local service that watches a local document folder, extracts embedded text where available, uses the shared `llm_ocr_skill` from `mn-skills` for scanned or low-text pages, classifies household finance activity, assesses cash-flow status and risks, uses a DockerWorker-only `w3m_browser_skill` phase for privacy-safe public research, and writes JSON plus Markdown advisor reports for human review each scan cycle.

Only the `research_financial_context` agent runs in DockerWorker. The DockerWorker image installs Python, `w3m`, `llm_ocr_skill`, `w3m_browser_skill`, and blueprint support for that research phase; all document intake, extraction, classification, assessment, and report-writing agents remain HostLocal.

## Quick Start

Run from the catalog:

```bash
mn run personal_financial_advisor
```

Run directly from this folder:

```bash
mn run --folder .
```

Direct runner bounded service smoke test:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --runs-root /tmp/mn-runs --run-id personal_financial_advisor-demo --watch --max-cycles 1
```

Direct runner continuous folder-watch service:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --input-folder ~/Documents/finance-inbox --watch --poll-interval 60
```

Direct runner one-shot scan, for local debugging only:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --input-folder ~/Documents/finance-inbox --once
```

## Inputs And Configuration

- `manifest.json`: service workflow contract, monitoring/review policy, runtime bindings, and product metadata.
- `config/default.json`: default OCR, continuous monitoring, output, and public sample settings.
- `inputs/public_dataset.json`: public downloadable dataset reference selected for sample inputs.
- `payloads/document_workflow/scripts/run_blueprint.py`: lightweight local runner demonstrating the OCR-backed extraction, browser research, folder polling, and runtime step-mode contract.
- `payloads/document_workflow/docker_worker/Dockerfile`: research-agent-only DockerWorker image with `w3m` and required skills installed.

## Browser Research

The advisor only sends generic public queries derived from risk categories and document types, such as fee review, cash-flow planning, debt review, and document organization. It must not send raw customer document text, account numbers, taxpayer IDs, names, or transaction descriptions to the web.

Membrane model compression is requested for research context packets with `use_model_compression=true`. The Membrane service must also run with `MN_CONTEXT_MODEL_COMPRESSION_ENABLED=true` and Docker Model Runner model `hf.co/homerquan/mn-context-engine-model-v-Q4_K_M`.

Default outputs are configured for `/Users/homer/Download/personal_financial_advisor`.

## Safety Checklist

- Keep real personal finance documents local unless an approved adapter explicitly allows transfer.
- Treat extracted values, reminders, and advice as review-only until a human approves them.
- Treat public browser research as general context, not personalized legal, tax, investment, or financial advice.
- Do not use outputs to move money, pay bills, place trades, file taxes, sync accounting systems, or share reports without qualified review.
- Review source dataset terms before downloading or redistributing public samples.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Public dataset note](inputs/public_dataset.json)
