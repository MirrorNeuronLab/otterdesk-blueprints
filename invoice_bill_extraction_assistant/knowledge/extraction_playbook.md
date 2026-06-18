# Invoice And Bill Extraction Playbook

Use this guidance as local retrieval context for accounts-payable extraction review.

## Extraction Priorities

- Preserve supplier name, customer name, invoice id, billing period, due date, totals, taxes, line items, consumption fields, and payment identifiers as source-grounded fields.
- Keep OCR confidence, extraction method, filename, page or region references, and redaction warnings attached to every material value.
- Treat blank, unreadable, contradictory, or low-confidence values as review-required rather than inferred.

## Validation Checks

- Compare subtotal, tax, adjustments, and total when the source provides enough structure.
- Flag due-date ambiguity, duplicate invoice ids, unsupported currency assumptions, missing supplier identity, and account or bank details that require redaction.
- Do not route extracted values to payment, ERP sync, or vendor updates without human approval.

## Tool Boundaries

- OCR and field extraction tools can propose values; the review packet remains the source of truth for human verification.
- Public dataset labels are fixtures for validation, not production evidence for a customer run.
