# Web lab sample inputs

`procedure.md` is a synthetic, simulation-only liquid-handling procedure. It
defines two plates, the starting water inventory, four numbered instructions
and three final volume goals. No physical samples or instruments are involved.

The primary source has 20 uL, less than the requested 100 uL transfer. The
procedure explicitly permits `source/A2`, which starts with 200 uL, as its only
alternate. A successful run uses that reserve, mixes the destination, advances
five virtual seconds and checks the tracked volume.

Expected final state:

| Well | Tracked volume (uL) |
| --- | --- |
| source/A1 | 20 |
| source/A2 | 100 |
| destination/A1 | 100 |

The run uses two fresh tips, leaving 94 unused tips. Model planning and adaptive
decisions remain live; this sample does not select a fake model or a prewritten
plan. The test suite keeps its expected plan in `tests/fixtures/`, outside the
published blueprint.

The default configuration and setup sample select
`@/examples/sample_inputs/procedure.md`. Edit a copy to try another procedure,
or provide your own Markdown text or file as described in the
[blueprint README](../../README.md). Review `plan.json`, `trace.json`,
`simulation.json`, `memory.json` and `report.md` after a run. Run the same hired
co-worker again to inspect how prior simulated outcomes enter its bounded
Membrane recall. The dataset inventory is recorded
in `SAMPLE_DATASET_MANIFEST.json`.
