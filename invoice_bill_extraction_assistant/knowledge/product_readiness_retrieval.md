# Invoice Extraction Retrieval Playbook

## Useful Retrieval Queries

- Which document pages and OCR snippets support supplier, invoice number, dates, line items, subtotal, tax, total, and due amount?
- Do extracted totals reconcile against line items and payment terms?
- Which fields are low confidence or require AP reviewer approval?

## Evidence Checklist

Every payable field must cite a source page, OCR snippet, coordinate, or document reference when available. Do not normalize supplier names, tax IDs, addresses, bank details, or totals beyond the supplied evidence. If a total does not reconcile, keep both values and flag the discrepancy instead of choosing silently.

Check invoice number, vendor, bill-to, ship-to, service period, utility meter period, due date, subtotal, taxes, fees, credits, total due, currency, and payment instructions. Treat ERP posting, payment release, and vendor onboarding as out-of-scope without human approval.

## Output Guidance

The final packet should include extracted fields, confidence, reconciliation status, missing fields, warnings, and AP next steps. Prefer "review before ERP/payment use" when fields are incomplete, inconsistent, or based on low-quality OCR.
