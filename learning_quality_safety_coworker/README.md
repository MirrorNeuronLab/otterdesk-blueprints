# Bibblio Learning & Safety Co-worker

Blueprint ID: bibblio_learning_safety_coworker

Business goal: Turn Bibblio into a profitable business.

This is one independent member of the bibblio-profitability-team collaboration group. It owns learning-objective review, age fit, claim safety, personalization minimization, and child-safety gates. It can run by itself and can exchange bounded, aggregate goal work packets with the other Bibblio co-workers through explicit MCP peer configurations.

## Workflow

1. review_learning_backlog creates the aspect analysis and a durable work packet.
2. publish_learning_safety_packet publishes a final, approval-ready aspect packet.

Input: a JSON backlog of candidate learning experiences.

Local working artifact: none.
Final artifact: learning_safety_packet.json.

## Control boundary

Therapeutic, diagnostic, medical, or guaranteed-outcome proposals are blocked. No review decision is a publication authorization.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/content_backlog.json. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run bibblio_learning_safety_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-profitable-business.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/learning_safety_playbook.md for the role contract.
