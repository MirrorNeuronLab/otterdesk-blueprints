# Bibblio Parent Lifecycle Co-worker

Blueprint ID: bibblio_parent_lifecycle_coworker

Business goal: Turn Bibblio into a profitable business.

This is one independent member of the bibblio-profitability-team collaboration group. It owns activation, retention, support friction, voice-of-parent synthesis, and draft lifecycle interventions. It can run by itself and can exchange bounded, aggregate goal work packets with the other Bibblio co-workers through explicit MCP peer configurations.

## Workflow

1. diagnose_parent_journey creates the aspect analysis and a durable work packet.
2. publish_parent_lifecycle_packet publishes a final, approval-ready aspect packet.

Input: a de-identified parent-feedback CSV.

Local working artifact: draft_parent_interventions.json.
Final artifact: parent_lifecycle_packet.json.

## Control boundary

It does not contact families. Copy, cohorts, frequency caps, and support escalation rules require approval, and raw family records are not shared through MCP.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/parent_feedback.csv. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run bibblio_parent_lifecycle_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-profitable-business.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/parent_lifecycle_playbook.md for the role contract.
