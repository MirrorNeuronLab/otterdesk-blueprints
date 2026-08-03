# Content Studio Co-worker

Blueprint ID: content_studio_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns small-batch content production planning, reuse, cost control, provenance, and QA handoff. It can run by itself and exchange bounded aggregate goal packets with explicitly approved peer co-workers.

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

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-business-success.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/content_studio_playbook.md for the role contract.
