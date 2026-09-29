# Counterevidence and uncertainty

**Section:** 21 · Evidence and confidence  
**Specification ID:** `AR-21-07`  
**Customer question:** What could make this finding or recommendation wrong?

## What to include

- Identify evidence that conflicts with the proposed interpretation or supports an alternative explanation.
- Describe missing data, assumptions, dynamic behavior, and environmental differences affecting the conclusion.
- Explain how these limits change confidence, scope, or the recommended next action.
- State what observation would distinguish competing explanations.

## Why this matters

Customers can make better decisions when the report shows the limits of its reasoning. Explicit counterevidence also prevents a one-sided review from turning a plausible pattern into an overstated conclusion.

## Evidence to use

Use contradictory code paths, tests, traces, history, documentation, and customer constraints alongside the supporting evidence.

## Expected report output

A counterevidence and uncertainty block attached to each significant finding, with alternative explanations and discriminating checks.

## Completion and quality checks

Do not bury material contradictions in a generic disclaimer. Distinguish evidence of absence from the absence of evidence and update the conclusion when counterevidence warrants it.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
