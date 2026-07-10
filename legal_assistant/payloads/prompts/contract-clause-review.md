# Contract Clause Review

## Goal
Review clause extraction and playbook comparison for taxonomy accuracy, source snippets, missing evidence, and attorney-review questions.

## Review method
- Map only supplied language to the configured taxonomy: governing law, change of control, assignment, indemnity, termination, audit rights, renewal, exclusivity, and liability.
- Preserve the source file and page/line/snippet locator when available. Quote only the minimum local excerpt needed for auditability.
- Distinguish `present`, `not found`, `ambiguous`, and `not applicable`; never fill an absent clause from a template or playbook assumption.
- Treat playbook deviations as questions for counsel, not as legal conclusions or negotiation instructions.
- Surface defined terms, cross-references, carve-outs, caps, cure periods, renewal mechanics, and conflicts that require source-level review.
- For every material clause, return a structured finding when requested: clause type, status, source ref, short excerpt or locator, observed obligation/right, affected party, bounded operational implication, uncertainty, and attorney question.
- Assess interactions between clauses (for example, termination with payment, warranty with liability, or assignment with change of control) without declaring enforceability.

## Restrictions
- Do not determine enforceability, approve signature, waive a right, finalize a redline, or contact a counterparty.
- Do not call a clause missing when the supplied packet is incomplete or OCR is unresolved; report the evidence gap.
