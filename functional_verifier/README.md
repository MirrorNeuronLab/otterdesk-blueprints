# Functional verifier

Trace analysis-document requirements to generated tests and implementation symbols. Compare the same protected case on both revisions. Inspect tests disabled or weakened by a change. Protected JSON Schema acceptance criteria can generate boundary and invalid-input cases and show which cases catch a removed constraint.

Set `min_coverage_percent` on an execution-record check when the scope requires a coverage floor. The report shows the runner's test counts, coverage and target.

Run `mn blueprint run ./functional_verifier --set inputs.payload.input_folder=/path/to/source` from the catalog, or select this co-worker in OtterDesk. Choose **Sample verification** for a ready-to-run example. Supply the optional verification scope in Settings or as a run configuration.

Sample scope

```json
{
  "checks": [
    {
      "id": "names",
      "kind": "schema_cases",
      "file": "input.schema.json",
      "requirement": "Accept named requests and reject requests without a name.",
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
      ]
    }
  ]
}
```

The JSON verdict includes the exact subject and plan, all required results and their attempts. The web and Markdown reports use the common offline template. The coordinator dispatches the same check contract as a native child task. A missing prerequisite or observation remains visible. See [the product contract](SPEC.md).
