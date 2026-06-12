# Medical De-Identification Record Intake Assistant

`Blueprint ID:` `medical_deid_record_intake_assistant`
`Category:` `Healthcare`

Detects and redacts PHI or PII from clinical-style PDFs, extracts patient-record intake fields, and writes a review-gated de-identification packet.

## Public Sample Input

- Dataset: RootCauseAnalytics Healthcare Library Sample
- Source: https://huggingface.co/datasets/RootCauseAnalytics/Healthcare-Library-Sample
- Expected files: *.pdf, ground_truth.csv, ground_truth.jsonl, bboxes.jsonl
- Note: Public synthetic healthcare document sample listed on Hugging Face with OCR-oriented PDFs and labels.

## What It Does

This OtterDesk blueprint stages a local document folder, extracts embedded text where available, uses the shared `llm_ocr_skill` from `mn-skills` for scanned or low-text pages, extracts structured fields, validates against public labels when available, and writes a review-only packet.

## Quick Start

Run from the catalog:

```bash
mn run medical_deid_record_intake_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Direct runner smoke test:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --runs-root /tmp/mn-runs --run-id medical_deid_record_intake_assistant-demo
```

## Inputs And Configuration

- `manifest.json`: workflow contract, review policy, runtime bindings, and product metadata.
- `config/default.json`: default OCR, LLM, output, and public dataset settings.
- `inputs/public_dataset.json`: public downloadable dataset reference selected for sample inputs.
- `payloads/document_workflow/scripts/run_blueprint.py`: lightweight local runner demonstrating the OCR-backed extraction contract.

Default outputs are configured for `/Users/homer/Download/medical_deid_record_intake_assistant`.

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
