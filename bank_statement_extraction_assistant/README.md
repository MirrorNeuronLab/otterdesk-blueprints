# Bank Statement Extraction Assistant

`Blueprint ID:` `bank_statement_extraction_assistant`
`Category:` `Finance`

Extracts bank statement account metadata, balances, transaction rows, debits, credits, fees, and validation checks from local statement PDFs.

## Public Sample Input

- Dataset: AgamiAI Indian Bank Statement Synthetic Dataset
- Source: https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements
- Expected files: *.pdf, *.json
- Note: Public synthetic bank statement dataset with scanned PDFs and structured JSON metadata.

## What It Does

This OtterDesk blueprint stages a local document folder, extracts embedded text where available, uses the shared `llm_ocr_skill` from `mn-skills` for scanned or low-text pages, extracts structured fields, validates against public labels when available, and writes a review-only packet.

## Quick Start

Run from the catalog:

```bash
mn run bank_statement_extraction_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Direct runner smoke test:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --runs-root /tmp/mn-runs --run-id bank_statement_extraction_assistant-demo
```

## Inputs And Configuration

- `manifest.json`: workflow contract, review policy, runtime bindings, and product metadata.
- `config/default.json`: default OCR, LLM, output, and public dataset settings.
- `inputs/public_dataset.json`: public downloadable dataset reference selected for sample inputs.
- `payloads/document_workflow/scripts/run_blueprint.py`: lightweight local runner demonstrating the OCR-backed extraction contract.

Default outputs are configured for `/Users/homer/Download/bank_statement_extraction_assistant`.

## Safety Checklist

- Review source dataset terms before downloading or redistributing samples.
- Keep real documents local unless an approved adapter explicitly allows transfer.
- Treat extracted values as review-only until a human approves them.
- Do not use outputs for filing, payment, legal, clinical, credit, or other consequential decisions without qualified review.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Public dataset note](inputs/public_dataset.json)
