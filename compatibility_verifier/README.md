# Compatibility verifier

The integration and regression section compares staged service journeys across the captured baseline and candidate. Each journey identifies the first divergent handoff and preserves its observed values.

Compare public Python exports and declared CLI entry points across revisions. Link customer-facing API, configuration, persisted-data or schema contracts to protected test cases. The report identifies the affected interface, source locations and whether evidence supports a regression or calls for a migration decision.

Python projects with `[project.scripts]` or `[project.gui-scripts]` receive an entry-point check. Use pinned installed-package and client tests for the deployment targets.

Run `mn blueprint run ./compatibility_verifier --set inputs.payload.input_folder=/path/to/source` from the catalog, or select this co-worker in OtterDesk. Choose **Sample verification** for a ready-to-run example. Supply the optional verification scope in Settings or as a run configuration.

Sample scope

```json
{
  "checks": [
    {
      "id": "protocol",
      "kind": "json_contract",
      "file": "wire.json",
      "keys": {
        "protocol": 2
      },
      "requirement": "Retain wire protocol 2."
    }
  ]
}
```

The JSON verdict includes the exact subject and plan, all required results and their attempts. The web and Markdown reports use the common offline template. The coordinator dispatches the same check contract as a native child task. A missing prerequisite or observation remains visible. See [the product contract](SPEC.md).

## WASI 0.3

Core schedules every step, owns retries and cancellation, and validates child plans. Each admitted step runs as a Rust WASI 0.3 command under Wasmtime. The SDK composes the six pinned WIT skills at submission. The phase can use the run-scoped artifact, model, approval, and mailbox imports granted in `execution.json`.
