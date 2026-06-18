# Tax Form OCR Capture Playbook

Use this guidance as local retrieval context for structured tax-form capture review.

## Capture Priorities

- Preserve form type, taxpayer identifiers, payer or employer identifiers, tax year, box or line labels, amounts, withholding, and source file references.
- Attach OCR method, field location, validation status, and warnings to every captured value.
- Treat blank, unreadable, conflicting, or low-confidence fields as review-required.

## Validation Checks

- Compare totals, withholding, payer ids, taxpayer ids, and year fields when labels make the relationship clear.
- Flag corrected forms, multi-page forms, partial crops, handwritten values, and classification uncertainty.
- Keep outputs review-only until a tax professional or taxpayer verifies them.

## Tool Boundaries

- OCR, form classification, field location, and answer validation tools assist intake only.
- Do not infer missing tax facts from surrounding context.
