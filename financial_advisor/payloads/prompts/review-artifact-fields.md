# Financial Review Artifact Fields

## Goal
Return a compact, source-grounded review artifact that a human can audit without reopening every downstream output.

## Instructions
- Include `summary`, `key_findings`, `review_questions`, `evidence_gaps`, `risk_flags`, `next_steps`, `confidence`, `review_only`, and `source_refs`.
- Make each finding an observation, a deterministic calculation interpretation, or a clearly labelled review question. Do not mix those categories.
- Tie `source_refs` to supplied local files or supplied public URLs. Never invent a citation, page, form box, or source name.
- Use `evidence_gaps` for absent, unreadable, stale, contradictory, or unvalidated inputs. An empty list is appropriate only when the supplied context supports that conclusion.
- Use `risk_flags` for concrete exposure or control issues, not generic warnings such as "be careful".
- Make `next_steps` bounded human-review tasks: identify the artifact to inspect, the question to answer, and the evidence needed.
- Calibrate `confidence` to evidence coverage and unresolved uncertainty on a 0–1 scale.

## Restrictions
- Keep `review_only` true.
- Do not add filing, trading, money movement, bill payment, account-opening/closing, or external-sharing recommendations.
- Do not change deterministic totals, OCR fields, portfolio metrics, or policy thresholds.
