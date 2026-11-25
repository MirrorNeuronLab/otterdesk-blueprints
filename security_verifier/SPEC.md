# Security verifier contract

The security and authorization section compares independently recorded allow and deny decisions with the approved actor, action and resource matrix. Static guard findings remain available in check evidence.

Review changes to registered permission checks, direct credential logging, dependencies and privileged CI actions. A pinned, dated advisory snapshot can identify exact affected package pins and local imports. The report distinguishes static exposure, observed enforcement and deployment details that still require evidence.

The standalone workflow captures staged UTF-8 source, executes the approved scope, and publishes JSON and Markdown plus an optional local HTML view. Its collaborative role is `security` in the `mn.verification.v1.assignment` and `mn.verification.v1.result` contracts. Source identity, plan, run, check and attempt must match.

A passing check needs at least one verified observation. The report lists excluded, blocked and inconclusive work. Pinned external evidence must match the selected suite, cases, target and subject. A retry preserves the first attempt. A changed candidate requires a fresh run. Scope and evidence are confidential and review-only.

The authorization view identifies the scope of function-, object-, service- and tenant-level evidence using versioned requirement IDs. The workflow check inspects effective job permissions and mutable action references. Deployment policy and advisory freshness are shown where evidence is available. [OWASP ASVS authorization requirements](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md) · [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).


## WASI 0.3 execution

Core schedules every step, owns retries and cancellation, and validates child plans. Each admitted step runs as a Rust WASI 0.3 command under Wasmtime. The SDK composes the six pinned WIT skills at submission. The phase can use the run-scoped artifact, model, approval, and mailbox imports granted in `execution.json`.
