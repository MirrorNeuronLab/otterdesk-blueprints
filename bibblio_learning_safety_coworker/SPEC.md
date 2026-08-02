# Bibblio Learning & Safety Co-worker v1 Specification

## Purpose

Own learning-objective review, age fit, claim safety, personalization minimization, and child-safety gates in service of the shared goal: Turn Bibblio into a profitable business.

## Independence contract

The blueprint declares exactly one domain specialist and two sequential steps: review_learning_backlog followed by publish_learning_safety_packet. It produces its own final artifact and does not depend on any other Bibblio blueprint to complete.

## Collaboration contract

The co-worker writes mirrorneuron.collaboration.goal-work-packet records with a stable goal_id, role and stage identity, source references, observed facts, assumptions, modeled analysis, recommendation, confidence, risks, requested approvals, outputs, and next check. MCP publication is job-scoped and bounded to the run directory. Peer reads are disabled by default and use only explicitly configured servers.

MCP does not select peers, route work, retry steps, decide completion, or approve actions.

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
