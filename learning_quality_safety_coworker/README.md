# Learning Quality & Safety Co-worker

Blueprint ID: learning_quality_safety_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns observable-value review, suitability, claim safety, personalization minimization, and release gates. It can run by itself and exchange bounded aggregate goal packets with explicitly approved peer co-workers.

## Workflow

1. review_learning_backlog creates the aspect analysis and a durable work packet.
2. publish_learning_safety_packet publishes a final, approval-ready aspect packet.

Input: a JSON backlog of candidate learning experiences.

Local working artifact: none.
Final role brief: `learning_quality_safety_packet.json` and `final_artifact.json`.

## Founder-facing output

The role brief contains a PASS/REVISE/BLOCK scorecard, decisions about evidence
standards and release authority, a 90-day quality plan, and explicit claim,
content-review, customer-feedback, and cost-capacity handoffs to peer roles.

## Control boundary

Therapeutic, diagnostic, medical, or guaranteed-outcome proposals are blocked. No review decision is a publication authorization.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/content_backlog.json. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run learning_quality_safety_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-business-success.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/learning_safety_playbook.md for the role contract.
