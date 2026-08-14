# Learning Quality & Safety Co-worker v1 Specification

## Purpose

Own observable-value review, suitability, claim safety, personalization minimization, and release gates for a configurable business and goal. The default Bibblio demo applies the generic role to early learning and child safety.

## Independence contract

The blueprint declares exactly one domain specialist and two sequential steps: review_learning_backlog followed by publish_learning_safety_packet. It produces its own final artifact and does not depend on any peer blueprint to complete.

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

OtterDesk supervision does not use that runtime service. The API-owned stable
job MCP remains available without an active run and exposes only bounded,
non-secret profile, schedule, lifecycle, and latest-run context. It cannot
start, configure, approve, or otherwise mutate this co-worker.

## Input and evidence contract

Input is a JSON backlog of candidate learning experiences. Synthetic fixtures are labeled synthetic_demo. User-supplied data is treated as confidential unless an operator explicitly classifies a derived aggregate otherwise. Missing evidence remains explicit and cannot be converted into an observed claim.

## Safety and approval contract

Therapeutic, diagnostic, medical, or guaranteed-outcome proposals are blocked. No review decision is a publication authorization.

## Acceptance criteria

- The source manifest expands and validates.
- Exactly one route-neutral agent executes both declared steps.
- The focused synthetic fixture produces a durable final artifact.
- The aspect packet contains evidence, assumptions, confidence, risks, approvals, and next-check fields.
- MCP exchange publication contains no credentials or forbidden private fields.
- The final artifact states that consequential external actions remain approval-required.
- The final role brief identifies all four peer-role handoffs and preserves bounded peer evidence when configured.
