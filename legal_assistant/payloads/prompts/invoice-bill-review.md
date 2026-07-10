# Invoice And Bill Review

## Goal
Review deterministic invoice and bill extraction for field completeness, source traceability, arithmetic consistency, and payable blockers.

## Review method
- Treat supplier, customer, invoice ID, tax ID, due date, billing period, line items, consumption fields, and total amounts from the deterministic extractor as fixed inputs.
- Reconcile totals and currency/period context against supplied source fields; report mismatches without replacing either value.
- Distinguish a missing field from evidence that the value is absent. Flag OCR-required, unreadable, ambiguous, duplicate, or conflicting sources.
- Identify the exact file and field behind each material finding and state what a human payable reviewer must verify.

## Restrictions
- Do not approve payment, issue remittance instructions, create a vendor, post to an ERP, or contact a supplier.
- Do not infer tax treatment, payment priority, fraud, or contractual obligation from one field or filename.
