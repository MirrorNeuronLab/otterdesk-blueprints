# Historical commit evidence

**Section:** 21 · Evidence and confidence  
**Specification ID:** `AR-21-04`  
**Customer question:** Which actual changes support the report’s evolutionary claims?

## What to include

- Record repository, commit or pull-request identifiers, timestamps, and analysis window.
- Describe the relevant changed components and the reason a change is included.
- State rename, merge, cherry-pick, bulk-change, and generated-code handling.
- Provide representative diffs and explain limits of classifying intent from messages or labels.

## Why this matters

Customers need to see the changes behind claims about churn, co-change, and accumulating responsibilities. Reproducible history handling prevents attractive trend charts from resting on misleading counts.

## Evidence to use

Use actual history and diffs at the reviewed repositories, with issue or review context only when available and authorized.

## Expected report output

A history evidence record with immutable change ID, relevant paths, time, classification, supporting detail, and filtering notes.

## Completion and quality checks

Do not invent change counts or treat commit messages as verified intent. Preserve missing-history limitations and do not infer individual performance from author activity.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
