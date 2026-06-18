# Medical De-Identification Retrieval Playbook

## Useful Retrieval Queries

- Which source text contains direct identifiers, quasi-identifiers, dates, locations, contact details, IDs, or rare clinical facts?
- Which redactions preserve clinical meaning while reducing re-identification risk?
- Which residual risks require privacy officer review before release?

## Evidence Checklist

Use the supplied clinical document, OCR text, label file, and de-identification policy as source evidence. Do not invent diagnoses, medications, encounters, or demographic facts. Preserve the distinction between clinical content and identifying content. If OCR is poor, flag the page as not safe for automated release.

Check names, initials, addresses, phone numbers, email, MRN, account numbers, claim numbers, dates, ages over policy threshold, facility names, clinician names, device identifiers, URLs, photos, and rare events. Review both direct identifiers and combinations that could re-identify a patient.

## Output Guidance

The final packet should include detected PHI, redaction actions, residual risk, source references, and privacy-officer next steps. Mark outputs as review-only and never claim HIPAA-safe release without authorized human review.
