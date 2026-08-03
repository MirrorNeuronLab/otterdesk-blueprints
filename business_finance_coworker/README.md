# Business Finance Co-worker

Blueprint ID: business_finance_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns unit economics, cash guardrails, break-even analysis, and finance evidence gaps. It can run by itself and exchange bounded aggregate goal packets with explicitly approved peer co-workers.

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

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-business-success.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/finance_playbook.md for the role contract.
