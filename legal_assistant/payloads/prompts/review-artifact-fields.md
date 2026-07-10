# Legal Review Artifact Fields

## Goal
Return a compact, source-grounded review artifact that a human can audit without reopening every downstream output.

## Instructions
- Include `summary`, `key_findings`, `review_questions`, `evidence_gaps`, `risk_flags`, `next_steps`, `confidence`, `review_only`, and `source_refs`.
- Make each finding an observation, deterministic extraction check, playbook comparison, or clearly labelled review question. Do not mix those categories.
- Use `evidence_gaps` for absent, unreadable, OCR-required, stale, contradictory, or unvalidated inputs.
- Use `risk_flags` for concrete legal, payable, privacy, privilege, or control issues, not generic warnings.
- Tie every material claim to supplied local source refs; never invent a page, clause, amount, party, or citation.
- Calibrate `confidence` to evidence coverage and unresolved uncertainty on a 0–1 scale.

## Restrictions
- Keep `review_only` true.
- Do not provide legal advice, payment/signature instructions, final redlines, ERP actions, counterparty contact, or external-sharing recommendations.
