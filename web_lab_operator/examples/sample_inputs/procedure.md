# Synthetic dilution series with reserve-source recovery

Simulation only. Prepare a three-point teaching dilution series, then transfer
aliquots into a separate readout plate. Track volumes and tips; do not calculate
concentrations or predict a physical assay result. Liquid names are nominal labels.
Use three 96-well 360 uL plates named source, dilution and readout, one channel,
and 96 fresh 300 uL tips. All unlisted wells start empty. Never reuse a tip.

## Starting inventory

| Well | Liquid | Initial volume (uL) |
| --- | --- | --- |
| source/A1 | training dye | 20 |
| source/A2 | training dye | 350 |
| source/B1 | diluent | 360 |
| source/B2 | diluent | 360 |

## Procedure

1. Transfer 320 uL to dilution/A1 using exactly one conditional transfer: use primary source/A1 if it holds at least 320 uL; otherwise use source/A2, the only allowed alternate, for the full 320 uL and leave source/A1 unchanged. Execute one branch, never both, and never combine sources. The stated starting inventory selects source/A2. Split this transfer into a 300 uL chunk and a 20 uL chunk, each with a fresh tip.
2. Transfer 180 uL from source/B1 to dilution/A2 using a fresh tip. No alternate source is allowed.
3. Transfer 180 uL from source/B2 to dilution/A3 using a fresh tip. No alternate source is allowed.
4. Mix dilution/A1 for 3 cycles of 200 uL per cycle using one fresh tip.
5. Transfer 60 uL from dilution/A1 to dilution/A2 using a fresh tip. No alternate source is allowed.
6. Mix dilution/A2 for 3 cycles of 120 uL per cycle using one fresh tip.
7. Transfer 60 uL from dilution/A2 to dilution/A3 using a fresh tip. No alternate source is allowed.
8. Mix dilution/A3 for 3 cycles of 120 uL per cycle using one fresh tip.
9. Transfer 40 uL from dilution/A1 to readout/A1 using a fresh tip. No alternate source is allowed.
10. Transfer 40 uL from dilution/A2 to readout/A2 using a fresh tip. No alternate source is allowed.
11. Transfer 40 uL from dilution/A3 to readout/A3 using a fresh tip. No alternate source is allowed.
12. Wait 5 virtual seconds. No physical incubation or reaction is simulated.
13. Check that dilution/A1 contains between 219.9 and 220.1 uL.
14. Check that dilution/A2 contains between 139.9 and 140.1 uL.
15. Check that dilution/A3 contains between 199.9 and 200.1 uL.
16. Check that readout/A1 contains between 39.9 and 40.1 uL.
17. Check that readout/A2 contains between 39.9 and 40.1 uL.
18. Check that readout/A3 contains between 39.9 and 40.1 uL.

## Final volume goals

- source/A1: 20 uL, tolerance 0.1 uL.
- source/A2: 30 uL, tolerance 0.1 uL.
- source/B1: 180 uL, tolerance 0.1 uL.
- source/B2: 180 uL, tolerance 0.1 uL.
- dilution/A1: 220 uL, tolerance 0.1 uL.
- dilution/A2: 140 uL, tolerance 0.1 uL.
- dilution/A3: 200 uL, tolerance 0.1 uL.
- readout/A1: 40 uL, tolerance 0.1 uL.
- readout/A2: 40 uL, tolerance 0.1 uL.
- readout/A3: 40 uL, tolerance 0.1 uL.
