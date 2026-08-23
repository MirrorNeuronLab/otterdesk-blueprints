# Learning Quality & Safety Co-worker

Blueprint ID: learning_quality_safety_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns observable-value review, suitability, claim safety, personalization minimization, and release gates. It runs independently, writes durable local role packets, and records cross-functional handoffs as requested evidence.

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

The top-level Job response service remains available before the first run and while idle, paused, scheduled, terminal, or archived. It answers bounded questions about role, safe configuration, progress, results, and missing evidence from sanitized Job context and Job-scoped RAG; asking a question never starts this co-worker.

See SPEC.md and payloads/knowledge/learning_safety_playbook.md for the role contract.
