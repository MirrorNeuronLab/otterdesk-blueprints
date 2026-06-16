# Invoice Bill Extraction Assistant

`Blueprint ID:` `invoice_bill_extraction_assistant`
`Category:` `Finance`

An invoice and bill extraction co-worker for accounts-payable review. Put invoice, bill, or utility PDF/JSON files in the input folder; it OCRs and extracts supplier, customer, invoice ID, tax, due date, total, line item, billing period, and consumption fields, then writes a review-only extraction packet and source-grounded report to the output folder.

## Public Sample Input

- Dataset: IDSEM Dataset
- Source: https://zenodo.org/records/6373179
- Expected files: *.pdf, *.json
- Note: Public Zenodo dataset with electricity bill PDFs and JSON labels; includes reduced preview subsets as described by the dataset record.

## What It Does

This OtterDesk blueprint stages a local document folder, extracts embedded text where available, uses the shared `llm_ocr_skill` from `mn-skills` for scanned or low-text pages, extracts structured fields, validates against public labels when available, and writes a review-only packet.

## Quick Start

Run from the catalog:

```bash
mn run invoice_bill_extraction_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Direct runner smoke test:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --runs-root /tmp/mn-runs --run-id invoice_bill_extraction_assistant-demo
```

## Inputs And Configuration

- `manifest.json`: workflow contract, review policy, runtime bindings, and product metadata.
- `config/default.json`: default OCR, LLM, output, and public dataset settings.
- `inputs/public_dataset.json`: public downloadable dataset reference selected for sample inputs.
- `payloads/document_workflow/scripts/run_blueprint.py`: lightweight local runner demonstrating the OCR-backed extraction contract.

Default outputs are configured for `outputs/invoice_bill_extraction_assistant`.

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
