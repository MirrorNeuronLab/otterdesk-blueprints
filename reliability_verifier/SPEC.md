# Reliability verifier contract

Trace recovery, concurrent work and integrity requirements to the generated tests that exercise them. Compare repeated observations with the same runner and fixtures. Use independently recorded event counts to check which operations actually repeated after a partial failure. The report identifies cleanup that masks exceptions, intermittent outcomes, resource measurements and unmet workload budgets.

The standalone workflow captures staged UTF-8 source, executes the approved scope, and publishes JSON and Markdown plus an optional local HTML view. Its collaborative role is `reliability` in the `mn.verification.v1.assignment` and `mn.verification.v1.result` contracts. Source identity, plan, run, check and attempt must match.

A passing check needs at least one verified observation. The report lists excluded, blocked and inconclusive work. Pinned external evidence must match the selected suite, cases, target and subject. A retry preserves the first attempt. A changed candidate requires a fresh run. Scope and evidence are confidential and review-only.
