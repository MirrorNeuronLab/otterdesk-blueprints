# Personal Legal Assistant

`personal_legal_assistant` merges invoice/bill extraction and contract clause review into one review-only local document workflow.

Put invoices, bills, contracts, clause notes, labels, or supporting files in the input folder. The blueprint extracts payable fields, maps contract clauses, compares playbook expectations, flags review issues, and writes a source-grounded packet to the output folder.

## Inputs

- `document_folder` or `input_folder`: local folder containing legal and payable documents.
- `output_folder`: defaults to `~/Downloads/personal_legal_assistant`.
- Optional `field_profile`, `matter_profile`, and `review_policy` values.

## Outputs

- Standard run-store files: `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, `final_artifact.json`.
- Domain artifacts: `invoice_bill_extraction.json`, `contract_clause_review.json`, `legal_issue_register.json`, `personal_legal_report.md`, `action_ledger.json`, `artifact_quality.json`, and `run_health.json`.

## Safety

Outputs are review-only. The assistant does not give legal advice, approve contracts, sign documents, post invoices, submit payment instructions, contact vendors or counterparties, or share private/privileged data externally.
