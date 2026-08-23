# Business Finance Co-worker

Blueprint ID: business_finance_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns unit economics, cash guardrails, break-even analysis, and finance evidence gaps. It runs independently, writes durable local role packets, and records cross-functional handoffs as requested evidence.

## Workflow

1. calculate_unit_economics creates the aspect analysis and a durable work packet.
2. publish_financial_control_packet publishes a final, approval-ready aspect packet.

Input: a dated JSON snapshot of customers, subscriptions, ARPU, gross margin, churn, acquisition spend, and operating costs. Generic customer fields are preferred; the unchanged Bibblio demo retains family-named fields.

Local working artifact: none.
Final role brief: `business_finance_packet.json` and `final_artifact.json`.

## Founder-facing output

The role brief contains a finance scorecard, experiment cash ceiling decisions,
a 90-day evidence plan, and named handoffs linking Growth channels, Lifecycle
retention, Content production cost, and Quality & Safety review workload.

## Control boundary

It provides decision support only. It cannot spend, move money, change pricing, file tax, sign contracts, or make accounting adjustments.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/business_metrics.json. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run business_finance_coworker

The top-level Job response service remains available before the first run and while idle, paused, scheduled, terminal, or archived. It answers bounded questions about role, safe configuration, progress, results, and missing evidence from sanitized Job context and Job-scoped RAG; asking a question never starts this co-worker.

See SPEC.md and payloads/knowledge/finance_playbook.md for the role contract.
