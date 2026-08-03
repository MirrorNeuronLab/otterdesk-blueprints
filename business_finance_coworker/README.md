# Bibblio Finance Co-worker

Blueprint ID: bibblio_finance_coworker

Business goal: Turn Bibblio into a profitable business.

This is one independent member of the bibblio-profitability-team collaboration group. It owns unit economics, cash guardrails, break-even analysis, and finance evidence gaps. It can run by itself and can exchange bounded, aggregate goal work packets with the other Bibblio co-workers through explicit MCP peer configurations.

## Workflow

1. calculate_unit_economics creates the aspect analysis and a durable work packet.
2. publish_financial_control_packet publishes a final, approval-ready aspect packet.

Input: a dated JSON snapshot of subscriptions, ARPU, gross margin, churn, acquisition spend, and operating costs.

Local working artifact: none.
Final artifact: financial_control_packet.json.

## Control boundary

It provides decision support only. It cannot spend, move money, change pricing, file tax, sign contracts, or make accounting adjustments.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/business_metrics.json. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run bibblio_finance_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-profitable-business.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/finance_playbook.md for the role contract.
