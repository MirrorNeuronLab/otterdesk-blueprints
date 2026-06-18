# Tax Form OCR Retrieval Playbook

## Useful Retrieval Queries

- Which source form image or OCR snippet supports each captured tax field?
- Does the captured form type match the expected labels and line/box names?
- Which fields need human review before downstream tax preparation?

## Evidence Checklist

Use supplied form images, OCR output, answer labels, and page references as the source of truth. Do not infer wages, withholding, payer IDs, taxpayer IDs, or form type from neighboring examples. Preserve redaction rules for identifiers and mark any unreadable box as low confidence.

Check form classification, tax year, payer/payee names, masked IDs, wages, federal withholding, state withholding, interest, dividends, retirement distributions, line references, totals, and document-page matching. If the answer profile and OCR disagree, return a discrepancy rather than overwriting evidence.

## Output Guidance

The capture packet should include field values, source references, confidence, validation status, redaction notes, and human-review questions. Keep it review-only and state that captured fields are not filing-ready until checked by a tax preparer.
