# Synthetic dilution series

This fictional, simulation-only procedure exercises three plates and 20 ordered
steps: reserve-source recovery, a transfer split across two fresh tips, a
three-point dilution sequence, nine mixing cycles, three readout aliquots, a
diluent-only blank, a virtual wait and seven tracked-volume checks. It predicts no chemistry or assay
results. All inventory, operations and final goals are explicit in `procedure.md`.

The 20 uL primary source cannot supply the requested 320 uL. The sole declared
reserve has 350 uL and supplies the complete transfer as 300 + 20 uL chunks.
The primary stays unchanged. Each transfer chunk and each mix uses a fresh tip.

Expected final state:

| Wells | Volume (uL each) |
| --- | --- |
| source/A1, source/A2 | 20, 30 |
| source/B1, source/B2 | 20, 140 |
| dilution/A1, dilution/A2, dilution/A3 | 220, 140, 200 |
| readout/A1, readout/A2, readout/A3, readout/B1 | 40, 40, 40, 40 |

A successful run has two adaptations, all eleven goals met and 83 unused tips.
Watch each pickup, aspiration, dispense, mixing half-cycle and check in Web lab.
After completion, review the saved step observations with the replay controls.
The planner and next-step decisions use the configured live model; expected
model responses live only in repository tests, outside the distributed package.

Step 12 encounters a second shortage: the earlier diluent transfer leaves only
20 uL in source/B1, too little for the 40 uL blank. The declared source/B2 reserve
supplies the complete amount. Chat reports each shortage before its transfer
and confirms each recovery after observing it. This is a seeded bookkeeping
risk, not a fabricated physical accident.

The workflow is adapted from PyLabRobot's [serial dilution and aliquot examples](https://discuss.pylabrobot.org/t/request-for-feedback-higher-level-methods-in-lh-aliquot-and-serial-dilution/138)
and [volume-tracker tutorial](https://docs.pylabrobot.org/0.2.1/user_guide/machine-agnostic-features/using-trackers.html).
Its fixed volumes and reserve policy are specific to this synthetic example.
