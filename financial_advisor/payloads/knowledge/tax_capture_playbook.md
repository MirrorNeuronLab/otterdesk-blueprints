# Tax Form OCR Capture Playbook

Use this guidance as local retrieval context for structured tax-form intake inside the unified financial advisor workflow. Capture is evidence organization, not tax preparation or filing approval.

## Capture Priorities

- Preserve form type, tax year, taxpayer and payer/employer field labels, amounts, withholding, box or line labels, source file, page, field location, extraction method, and confidence.
- Keep the original image and any companion answer file paired by source stem or an explicit matching key; record the matching decision.
- Attach validation status and warnings to every captured field or field group, not only to the form-level record.
- Treat blank, unreadable, conflicting, cropped, handwritten, or low-confidence fields as review-required.

## Validation Checks

- Compare tax year, form class, repeated identifiers, withholding, and totals only when the source labels make the relationship clear.
- Flag corrected forms, duplicate forms, multi-page forms with missing pages, partial crops, unsupported form classes, and answer files without a matching source image.
- Separate "field captured" from "field validated". A companion answer file can support capture but cannot replace source-image verification.
- Preserve conflicts rather than selecting the value that makes a total look plausible.
- Treat missing forms or fields as evidence gaps; do not infer them from filenames, neighboring labels, or common tax patterns.

## Quality States

- `matched_companion_answer_file`: image and answer evidence are paired, but material fields still require source review before tax use.
- `needs_manual_ocr_or_answer_file`: image exists without sufficient structured support.
- `answer_file_without_matching_source_image`: structured data exists without the source image needed to verify it.
- `review_required`: any material warning, conflict, low confidence, unsupported class, or incomplete source coverage remains unresolved.

## Tool Boundaries

- OCR, form classification, field location, and answer validation tools assist intake only.
- Do not infer missing tax facts, tax treatment, eligibility, deductions, or filing positions from surrounding context.
- Do not expose taxpayer identifiers or raw form text in public queries.
- Keep outputs review-only until a taxpayer or qualified tax professional verifies the source fields and applicable current rules.
