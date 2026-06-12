# Legal Contract Clause Review Assistant

`Blueprint ID:` `legal_contract_clause_review_assistant`
`Category:` `Legal`

Reviews local contract PDFs, extracts important clauses, compares them with a playbook, and writes a source-grounded legal review packet.

## Public Sample Input

- Dataset: Contract Understanding Atticus Dataset (CUAD) v1
- Source: https://zenodo.org/records/4595826
- Expected files: full_contracts_pdf/*.pdf, full_contracts_txt/*.txt, *.csv, *.json
- Note: Public dataset with 510 commercial contracts and 13,000+ labels across 41 clause types.

## What It Does

This OtterDesk blueprint stages a local document folder, extracts embedded text where available, uses the shared `llm_ocr_skill` from `mn-skills` for scanned or low-text pages, extracts structured fields, validates against public labels when available, and writes a review-only packet.

## Quick Start

Run from the catalog:

```bash
mn run legal_contract_clause_review_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Direct runner smoke test:

```bash
python3.11 payloads/document_workflow/scripts/run_blueprint.py --runs-root /tmp/mn-runs --run-id legal_contract_clause_review_assistant-demo
```

## Inputs And Configuration

- `manifest.json`: workflow contract, review policy, runtime bindings, and product metadata.
- `config/default.json`: default OCR, LLM, output, and public dataset settings.
- `inputs/public_dataset.json`: public downloadable dataset reference selected for sample inputs.
- `payloads/document_workflow/scripts/run_blueprint.py`: lightweight local runner demonstrating the OCR-backed extraction contract.

Default outputs are configured for `/Users/homer/Download/legal_contract_clause_review_assistant`.

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
