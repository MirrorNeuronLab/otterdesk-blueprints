# Compatibility verifier contract

Compare public Python exports and declared CLI entry points across revisions. Link customer-facing API, configuration, persisted-data or schema contracts to protected test cases. The report identifies the affected interface, source locations and whether evidence supports a regression or calls for a migration decision.

The standalone workflow captures staged UTF-8 source, executes the approved scope, and publishes JSON and Markdown plus an optional local HTML view. Its collaborative role is `compatibility` in the `mn.verification.v1.assignment` and `mn.verification.v1.result` contracts. Source identity, plan, run, check and attempt must match.

A passing check needs at least one verified observation. The report lists excluded, blocked and inconclusive work. Pinned external evidence must match the selected suite, cases, target and subject. A retry preserves the first attempt. A changed candidate requires a fresh run. Scope and evidence are confidential and review-only.
