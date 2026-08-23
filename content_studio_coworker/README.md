# Content Studio Co-worker

Blueprint ID: content_studio_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns small-batch content production planning, reuse, cost control, provenance, and QA handoff. It runs independently, writes durable local role packets, and records cross-functional handoffs as requested evidence.

## Workflow

1. plan_content_batch creates the aspect analysis and a durable work packet.
2. publish_content_studio_packet publishes a final, approval-ready aspect packet.

Input: JSON learning briefs already marked PASS or PASS WITH CONDITIONS.

Local working artifact: draft_content_packages.json.
Final role brief: `content_studio_packet.json` and `final_artifact.json`.

## Founder-facing output

The role brief contains a production scorecard, batch and release decisions, a
90-day build/test plan, and named handoffs connecting approved briefs, customer
content gaps, Growth proof assets, and Finance unit-cost constraints.

## Control boundary

It creates draft package structures only. Every complete package returns to learning, safety, brand, accessibility, licensing, and founder review before release.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/approved_learning_briefs.json. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run content_studio_coworker

The top-level Job response service remains available before the first run and while idle, paused, scheduled, terminal, or archived. It answers bounded questions about role, safe configuration, progress, results, and missing evidence from sanitized Job context and Job-scoped RAG; asking a question never starts this co-worker.

See SPEC.md and payloads/knowledge/content_studio_playbook.md for the role contract.
