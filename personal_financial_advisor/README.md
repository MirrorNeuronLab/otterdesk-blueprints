# Personal Financial Advisor

`Blueprint ID:` `personal_financial_advisor`
`Category:` `Finance`

Continuously monitors a local personal finance folder with actor-style default-LLM specialists, OCRs statements, income documents, receipts, bills, and related records, researches public financial guidance with an LLM-guided `w3m_browser_skill` market researcher, then writes review-only household finance status, advice, risk reminders, and source-grounded reports.

## Public Sample Input

- Dataset: AgamiAI Indian Bank Statement Synthetic Dataset
- Source: https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements
- Expected files: PDF, image, TXT, JSON, and CSV finance documents
- Note: The bundled public sample is a synthetic bank statement subset. Real runs can include income records, bank statements, receipts, bills, credit-card statements, loan records, and similar local finance files.

## What It Does

This OtterDesk blueprint runs as a continuous local service made of collaborating actors: `financial_folder_watcher`, `financial_document_reader`, `financial_activity_classifier`, `financial_health_assessor`, `financial_market_researcher`, and `financial_advice_reporter`. Each actor uses the configured default LLM with deterministic fallback evidence, while the shared `llm_ocr_skill` handles scanned or low-text pages.

Only the `financial_market_researcher` agent runs in DockerWorker. It uses the default LLM to plan privacy-safe public searches, starts from DuckDuckGo, browses selected pages through `w3m_browser_skill`, and hands source-grounded findings to the other actors. The document intake, extraction, classification, assessment, and report-writing actors remain HostLocal.

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
- `payloads/document_workflow/docker_worker/Dockerfile`: research-agent-only DockerWorker image with `w3m`; required local skill packages are staged from `MN_SKILLS_ROOT` at build time and installed into the image.

## Browser Research

The market researcher only sends generic public queries derived from risk categories and document types, such as fee review, cash-flow planning, debt review, and document organization. It must not send raw customer document text, account numbers, taxpayer IDs, names, or transaction descriptions to the web.

Membrane model compression is requested for research context packets with `use_model_compression=true`. The Membrane service must also run with `MN_CONTEXT_MODEL_COMPRESSION_ENABLED=true` and Docker Model Runner model `hf.co/homerquan/mn-context-engine-model-v-Q4_K_M`.

Default outputs are configured for `outputs/personal_financial_advisor`.

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
