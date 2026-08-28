# Robotics simulation infrastructure notes (in-progress)

This folder is intentionally half-complete, modeling an active researcher workspace.

Scope in play: build a shared robotics simulation platform that can support manipulation, navigation, and multi-robot coordination teams with lower duplication and clearer experimental comparability.

## What is already in the folder

- `global_robotics_roadmap_2025.pdf` is retained as the canonical planning anchor.
- `baseline_measurements.csv` is a synthetic baseline table with run-level metrics for three simulator stacks.
- `sample_research_request.json` now frames a robotics-domain question for architecture choices, not operational cooling controls.

## Current findings

- Preliminary read suggests the highest leverage is not just raw speed; it is **scenario determinism** (seeded randomization, standardized scene descriptors, and fixed benchmark contracts).
- Two stacks currently look promising:
  - A containerized Isaac-style workflow for photoreal and manipulation-heavy tasks.
  - A lighter Gazebo/Mujoco setup for large-scale throughput and CI execution.
- A remaining blind spot is **transferability**: simulation gains from one benchmark have not been validated for policy behavior on hardware.

## Working assumptions and constraints

- No live robots or production simulators will be changed in this phase.
- Pilot success is measured by repeatability and analysis time, not only wall-clock speed.
- Current local baseline data is synthetic and does not include a real compute reservation policy.

## Draft hypotheses to challenge

1. Shared container images plus pinned ROS 2 distributions reduce onboarding time for new robots.
2. A central scenario schema can make success-rate comparisons between teams interpretable.
3. Enforcing artifact-level provenance on each run lowers review friction later in the pipeline.

Open concerns: version lock-in, license compatibility across stacks, and whether benchmark realism degrades too much when speed is optimized.

## Next steps

- Add a short reproducibility memo for each benchmark scene and publish runbook deltas.
- Add two follow-up artifact files: a scene-change log and a risk register.
- Run a mini adversarial review pass on every candidate architecture with explicit disconfirming metrics.
