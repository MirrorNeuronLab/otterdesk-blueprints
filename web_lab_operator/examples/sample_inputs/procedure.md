# Synthetic transfer with a reserve source

Simulation only. Prepare water in a destination plate and inspect the tracked volumes.
Use two 96-well 360 uL plates named source and destination, and fresh 300 uL tips.
All unlisted wells are empty. Liquid identity water is a nominal simulation label.

| Well | Liquid | Initial volume (uL) |
| --- | --- | --- |
| source/A1 | water | 20 |
| source/A2 | water | 200 |

## Procedure

1. Transfer 100 uL from source/A1 to destination/A1. If source/A1 has insufficient liquid, use source/A2 instead; it is the only allowed alternate source.
2. Mix destination/A1 twice with 50 uL per cycle using one fresh tip.
3. Wait 5 virtual seconds. No physical incubation or reaction is simulated.
4. Check that destination/A1 contains between 99.9 and 100.1 uL.

## Final volume goals

- destination/A1: 100 uL, tolerance 0.1 uL.
- source/A1: 20 uL, tolerance 0.1 uL.
- source/A2: 100 uL, tolerance 0.1 uL.
