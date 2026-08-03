# Bibblio Content Studio Co-worker

Blueprint ID: bibblio_content_studio_coworker

Business goal: Turn Bibblio into a profitable business.

This is one independent member of the bibblio-profitability-team collaboration group. It owns small-batch content production planning, reuse, cost control, provenance, and QA handoff. It can run by itself and can exchange bounded, aggregate goal work packets with the other Bibblio co-workers through explicit MCP peer configurations.

## Workflow

1. plan_content_batch creates the aspect analysis and a durable work packet.
2. publish_content_studio_packet publishes a final, approval-ready aspect packet.

Input: JSON learning briefs already marked PASS or PASS WITH CONDITIONS.

Local working artifact: draft_content_packages.json.
Final artifact: content_studio_packet.json.

## Control boundary

It creates draft package structures only. Every complete package returns to learning, safety, brand, accessibility, licensing, and founder review before release.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/approved_learning_briefs.json. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run bibblio_content_studio_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-profitable-business.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/content_studio_playbook.md for the role contract.
