# Business Finance Co-worker v1 Specification

## Purpose

Own unit economics, cash guardrails, break-even analysis, and finance evidence gaps for a configurable business and goal. The default demo business is Bibblio and its default goal is "Build a successful business for Bibblio."

## Independence contract

The blueprint declares exactly one domain specialist and two sequential steps: calculate_unit_economics followed by publish_financial_control_packet. It produces its own final artifact and does not depend on any peer blueprint to complete.

## Collaboration contract

The co-worker writes mirrorneuron.collaboration.goal-work-packet records with a stable goal_id, role and stage identity, source references, observed facts, assumptions, modeled analysis, recommendation, confidence, risks, requested approvals, outputs, and next check. MCP publication is job-scoped and bounded to the run directory. Peer reads are disabled by default and use only explicitly configured servers.

The final step re-reads bounded peer packets and carries them into a founder-facing
role brief. That brief must include `role_contribution`, `north_star_question`,
`role_scorecard`, `founder_decisions`, `ninety_day_plan`, and
`cross_functional_handoffs`. With no peer packets, it explicitly reports the
evidence dependencies that remain unresolved; a peer recommendation never counts
as human approval.

MCP does not select peers, route work, retry steps, decide completion, or approve actions.
Each active run also supervises a loopback `mn-job-collaboration` service with
the `mcp` and `job-collaboration` tags. It publishes bounded staged status
transitions and existing staged/final work packets for OtterDesk and explicitly
approved same-node peers. The service is read-only and ends with the run.

## Input and evidence contract

Input is a dated JSON snapshot of subscriptions, customer funnel counts, ARPU, gross margin, churn, refunds, acquisition spend, and operating costs. Generic customer field names are preferred; the unchanged Bibblio fixture retains its family-named fields. Synthetic fixtures are labeled synthetic_demo. User-supplied data is treated as confidential unless an operator explicitly classifies a derived aggregate otherwise. Missing evidence remains explicit and cannot be converted into an observed claim.

## Safety and approval contract

It provides decision support only. It cannot spend, move money, change pricing, file tax, sign contracts, or make accounting adjustments.

## Acceptance criteria

- The source manifest expands and validates.
- Exactly one route-neutral agent executes both declared steps.
- The focused synthetic fixture produces a durable final artifact.
- The aspect packet contains evidence, assumptions, confidence, risks, approvals, and next-check fields.
- MCP exchange publication contains no credentials or forbidden private fields.
- The final artifact states that consequential external actions remain approval-required.
- The final role brief identifies all four peer-role handoffs and preserves bounded peer evidence when configured.
