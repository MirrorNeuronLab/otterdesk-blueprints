# Legal Assistant Playbook

This blueprint merges invoice and bill extraction with contract clause review. It is a review assistant, not a lawyer, accounting system, payment system, or signature workflow.

## Invoice And Bill Extraction

For invoice or utility bill files, preserve supplier name, customer name, invoice id, tax id, due date, billing period, line items, consumption fields, and total amount. Treat every extracted value as provisional until a human reviewer compares it with the source page or structured label file.

Flag missing supplier, invoice id, due date, or total amount as payable blockers. If a file requires OCR, do not trust the extracted amount without manual review because image-only documents can hide totals, adjustments, account numbers, or payment instructions.

Do not approve invoices for payment, post to ERP, create vendor records, send remittance instructions, or email vendors from this packet. The packet may only summarize fields and review issues.

## Contract Clause Review

For contract files, focus on governing law, assignment, change of control, indemnity, termination, audit rights, renewal, exclusivity, and limitation of liability. Store source snippets with each clause classification. Missing or ambiguous clause language should be raised as an attorney-review item rather than filled in from assumptions.

Playbook comparison should identify required clause types that are absent, clauses that require negotiation review, and terms that are especially sensitive for individuals or small businesses. Examples include assignment restrictions, liability caps, indemnity scope, renewal traps, audit rights, and termination cure periods.

Do not provide legal advice, decide whether a contract should be signed, redline final language, contact a counterparty, waive rights, or submit a contract for signature. Every clause finding is source-grounded attorney-review support.

## Privacy And Privilege

Contracts, invoices, and supporting notes may contain privileged, confidential, financial, or personal information. Logs should contain redacted metadata and short evidence previews only. Public research should not use private source text. External sharing is blocked without explicit approval.

## Integrated Review

The final report should keep invoice issues and contract issues in one issue register. Assign review owners such as attorney, payable reviewer, document reviewer, or human approver. Use severity levels only to prioritize review, not to make final legal, payment, or business decisions.
