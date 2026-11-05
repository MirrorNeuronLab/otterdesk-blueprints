# Synthetic dilution series

This fictional, simulation-only procedure exercises three plates and 18 ordered
steps: reserve-source recovery, a transfer split across two fresh tips, a
three-point dilution sequence, nine mixing cycles, three readout aliquots, a
virtual wait and six tracked-volume checks. It predicts no chemistry or assay
results. All inventory, operations and final goals are explicit in `procedure.md`.

The 20 uL primary source cannot supply the requested 320 uL. The sole declared
reserve has 350 uL and supplies the complete transfer as 300 + 20 uL chunks.
The primary stays unchanged. Each transfer chunk and each mix uses a fresh tip.

Expected final state:

| Wells | Volume (uL each) |
| --- | --- |
| source/A1, source/A2 | 20, 30 |
| source/B1, source/B2 | 180, 180 |
| dilution/A1, dilution/A2, dilution/A3 | 220, 140, 200 |
| readout/A1, readout/A2, readout/A3 | 40, 40, 40 |

A successful run has one adaptation, all ten goals met and 84 unused tips.
Watch each pickup, aspiration, dispense, mixing half-cycle and check in Web lab.
After completion, review the saved step observations with the replay controls.
The planner and next-step decisions use the configured live model; expected
model responses live only in repository tests, outside the distributed package.
