# Medical De-Identification Playbook

Use this guidance as local retrieval context for PHI/PII detection and medical-record intake.

## PHI Handling

- Treat names, dates, locations, contact details, identifiers, account numbers, device ids, URLs, photos, signatures, and rare clinical combinations as review-sensitive.
- Preserve source file, page or region hints, extraction method, and redaction confidence for each finding.
- Keep raw clinical text out of logs and public queries.

## Review Checks

- Flag uncertain PHI, overlapping bounding boxes, OCR gaps, handwritten text risk, and context-dependent identifiers.
- Distinguish a de-identification suggestion from a completed de-identification decision.
- Require human privacy review before downstream sharing, analytics, or model training.

## Tool Boundaries

- OCR, PHI detection, and redaction validation are assistive tools.
- If source evidence is unreadable or ambiguous, mark the field review-required rather than guessing.
