# Reliability verifier

Trace recovery, concurrent work and integrity requirements to the generated tests that exercise them. Compare repeated observations with the same runner and fixtures. The report identifies cleanup that masks exceptions, intermittent outcomes, resource measurements and unmet workload budgets.

Set `max_elapsed_ms` on an execution-record check to enforce a runner budget. The receipt supplies the elapsed time for that suite on the recorded target.

Run `mn blueprint run ./reliability_verifier --set inputs.payload.input_folder=/path/to/source` from the catalog, or select this co-worker in OtterDesk. Choose **Sample verification** for a ready-to-run example. Supply the optional verification scope in Settings or as a run configuration.

Sample scope

```json
{
  "checks": [
    {
      "id": "name-workload",
      "kind": "schema_workload",
      "file": "input.schema.json",
      "cases": [
        {
          "id": "valid-name",
          "input": {
            "name": "Ada"
          },
          "accept": true
        },
        {
          "id": "missing-name",
          "input": {},
          "accept": false
        }
      ],
      "max_p95_ms": 100,
      "requirement": "The two example validations take at most 100 ms at p95 on this runner."
    }
  ]
}
```

The JSON verdict includes the exact subject and plan, all required results and their attempts. The web and Markdown reports use the common offline template. The coordinator dispatches the same check contract as a native child task. A missing prerequisite or observation remains visible. See [the product contract](SPEC.md).
