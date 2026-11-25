# Security verifier

The security and authorization section compares independently recorded allow and deny decisions with the approved actor, action and resource matrix. Static guard findings remain available in check evidence.

Review changes to registered permission checks, direct credential logging, dependencies and privileged CI actions. A pinned, dated advisory snapshot can identify exact affected package pins and local imports. The report distinguishes static exposure, observed enforcement and deployment details that still require evidence.

Use independently pinned suite records to include authentication and other protection checks. The report ties each result to the supplied runner target.

Run `mn blueprint run ./security_verifier --set inputs.payload.input_folder=/path/to/source` from the catalog, or select this co-worker in OtterDesk. Choose **Sample verification** for a ready-to-run example. Supply the optional verification scope in Settings or as a run configuration.

Sample scope

```json
{
  "checks": []
}
```

The JSON verdict includes the exact subject and plan, all required results and their attempts. The web and Markdown reports use the common offline template. The coordinator dispatches the same check contract as a native child task. A missing prerequisite or observation remains visible. See [the product contract](SPEC.md).

## WASI 0.3

Core schedules every step, owns retries and cancellation, and validates child plans. Each admitted step runs as a Rust WASI 0.3 command under Wasmtime. The SDK composes the six pinned WIT skills at submission. The phase can use the run-scoped artifact, model, approval, and mailbox imports granted in `execution.json`.
