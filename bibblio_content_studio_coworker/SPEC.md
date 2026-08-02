# Bibblio Content Studio Co-worker v1 Specification

## Purpose

Own small-batch content production planning, reuse, cost control, provenance, and QA handoff in service of the shared goal: Turn Bibblio into a profitable business.

## Independence contract

The blueprint declares exactly one domain specialist and two sequential steps: plan_content_batch followed by publish_content_studio_packet. It produces its own final artifact and does not depend on any other Bibblio blueprint to complete.

## Collaboration contract

The co-worker writes mirrorneuron.collaboration.goal-work-packet records with a stable goal_id, role and stage identity, source references, observed facts, assumptions, modeled analysis, recommendation, confidence, risks, requested approvals, outputs, and next check. MCP publication is job-scoped and bounded to the run directory. Peer reads are disabled by default and use only explicitly configured servers.

MCP does not select peers, route work, retry steps, decide completion, or approve actions.

## Input and evidence contract

Input is JSON learning briefs already marked PASS or PASS WITH CONDITIONS. Synthetic fixtures are labeled synthetic_demo. User-supplied data is treated as confidential unless an operator explicitly classifies a derived aggregate otherwise. Missing evidence remains explicit and cannot be converted into an observed claim.

## Safety and approval contract

It creates draft package structures only. Every complete package returns to learning, safety, brand, accessibility, licensing, and founder review before release.

## Acceptance criteria

- The source manifest expands and validates.
- Exactly one route-neutral agent executes both declared steps.
- The focused synthetic fixture produces a durable final artifact.
- The aspect packet contains evidence, assumptions, confidence, risks, approvals, and next-check fields.
- MCP exchange publication contains no credentials or forbidden private fields.
- The final artifact states that consequential external actions remain approval-required.
