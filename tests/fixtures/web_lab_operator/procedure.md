# Synthetic transfer with a reserve source

Simulation only. Prepare water in a destination plate and inspect the tracked volumes.
Use two 96-well 360 uL plates named source and destination, and fresh 300 uL tips.
All unlisted wells are empty. Liquid identity water is a nominal simulation label.

| Well | Liquid | Initial volume (uL) |
| --- | --- | --- |
| source/A1 | water | 20 |
| source/A2 | water | 200 |

## Procedure

1. Transfer 100 uL to destination/A1 using exactly one conditional transfer: use primary source/A1 if it holds at least 100 uL; otherwise use source/A2, the only allowed alternate, for the full 100 uL and leave source/A1 unchanged. Execute one branch, never both, and never combine sources. With the stated initial inventory (source/A1 holds 20 uL), the alternate branch applies.
2. Mix destination/A1 twice with 50 uL per cycle using one fresh tip.
3. Wait 5 virtual seconds. No physical incubation or reaction is simulated.
4. Check that destination/A1 contains between 99.9 and 100.1 uL.

## Final volume goals

- destination/A1: 100 uL, tolerance 0.1 uL.
- source/A1: 20 uL, tolerance 0.1 uL.
- source/A2: 100 uL, tolerance 0.1 uL.
