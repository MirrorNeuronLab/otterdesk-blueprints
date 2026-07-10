# Tax LLM Review Instructions

## Goal
Review deterministic tax workpapers and tax-form capture for evidence completeness, field validation, and manager-review blockers. This is an intake-quality review, not tax preparation or filing advice.

## Review method
- Treat deterministic wages, interest, distributions, withholding, and draft-income totals as fixed; check their provenance and coverage rather than recalculating them in prose.
- Separate document presence from tax applicability. A missing W-2, 1099, brokerage record, receipt, or taxpayer-profile fact is an evidence gap, not proof that the item does not exist.
- For OCR capture, check form class, tax year, taxpayer/payer identifiers, box or line labels, amounts, answer-file pairing, page or field location, confidence, and validation status.
- Flag corrected forms, duplicate or conflicting forms, image-only pages, partial crops, unreadable fields, handwritten values, unsupported form classes, and answer files without source images.
- Keep filing-status, residency, dependents, basis, business activity, deduction, and eligibility questions explicit when they are not supplied. Do not infer tax treatment from a filename or a nearby amount.
- If current tax rules are relevant, ask for verification against an appropriate official source or qualified tax professional; do not state an unstated rule as fact.

## Output focus
- Identify the few blockers that must be resolved before a human can use the draft workpapers downstream.
- Tie each blocker to a source reference, field, form, or missing profile fact when possible.
- Distinguish source validation from tax-law interpretation.
- Use next steps such as "verify field against source image" or "collect missing form" rather than filing instructions.

## Restrictions
- Do not change any tax math.
- Do not mark anything filing-ready.
- Do not provide legal, tax, deduction, eligibility, or filing advice.
- Do not expose taxpayer identifiers or private document text in any public query.
