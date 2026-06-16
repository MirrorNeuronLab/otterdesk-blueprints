# Tax Form OCR Capture Assistant

`Blueprint ID:` `tax_form_ocr_capture_assistant`
`Category:` `Finance`

A tax-form OCR co-worker for structured intake review. Put tax form images, PDFs, answer files, or field-context tables in the input folder; it classifies forms, locates fields, captures taxpayer and line-item values, validates totals, and writes a review-only tax capture packet to the output folder.

## Public Sample Input

- Dataset: NIST Special Database 2 and NIST Special Database 6
- Source: https://www.nist.gov/srd/nist-special-database-2
- Expected files: *.png, *.fmt, field context tables
- Note: Public NIST structured-form reference sets with simulated tax submissions, form images, and answer files.

## What It Does

This OtterDesk blueprint stages a local document folder, extracts embedded text where available, uses the shared `llm_ocr_skill` from `mn-skills` for scanned or low-text pages, extracts structured fields, validates against public labels when available, and writes a review-only packet.

## Quick Start

Run from the catalog:

```bash
mn run tax_form_ocr_capture_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Direct runner smoke test:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --runs-root /tmp/mn-runs --run-id tax_form_ocr_capture_assistant-demo
```

## Inputs And Configuration

- `manifest.json`: workflow contract, review policy, runtime bindings, and product metadata.
- `config/default.json`: default OCR, LLM, output, and public dataset settings.
- `inputs/public_dataset.json`: public downloadable dataset reference selected for sample inputs.
- `payloads/document_workflow/scripts/run_blueprint.py`: lightweight local runner demonstrating the OCR-backed extraction contract.

Default outputs are configured for `outputs/tax_form_ocr_capture_assistant`.

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
