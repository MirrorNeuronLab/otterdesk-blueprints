# Compatibility verifier

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
