# Compatibility verifier contract

The integration and regression section compares staged service journeys across the captured baseline and candidate. Each journey identifies the first divergent handoff and preserves its observed values.

Compare public Python exports and declared CLI entry points across revisions. Link customer-facing API, configuration, persisted-data or schema contracts to protected test cases. The report identifies the affected interface, source locations and whether evidence supports a regression or calls for a migration decision.

The standalone workflow captures staged UTF-8 source, executes the approved scope, and publishes JSON and Markdown plus an optional local HTML view. Its collaborative role is `compatibility` in the `mn.verification.v1.assignment` and `mn.verification.v1.result` contracts. Source identity, plan, run, check and attempt must match.

A passing check needs at least one verified observation. The report lists excluded, blocked and inconclusive work. Pinned external evidence must match the selected suite, cases, target and subject. A retry preserves the first attempt. A changed candidate requires a fresh run. Scope and evidence are confidential and review-only.


## WASI 0.3 execution

Core schedules every step, owns retries and cancellation, and validates child plans. Each admitted step runs as a Rust WASI 0.3 command under Wasmtime. The SDK composes the six pinned WIT skills at submission. The phase can use the run-scoped artifact, model, approval, and mailbox imports granted in `execution.json`.
