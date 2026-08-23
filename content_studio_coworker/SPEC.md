# Content Studio Co-worker v1 Specification

## Purpose

Own small-batch content production planning, reuse, cost control, provenance, and QA handoff for a configurable business and goal. The default demo business is Bibblio and its default goal is "Build a successful business for Bibblio."

## Independence contract

The blueprint declares exactly one domain specialist and two sequential steps: plan_content_batch followed by publish_content_studio_packet. It produces its own final artifact and does not depend on any peer blueprint to complete.

## Durable work-packet and response contract

Each run writes durable `mn.goal.work_packet.v1` records with its stable goal, role, stage, source references, observed facts, assumptions, recommendation, confidence, risks, requested approvals, outputs, and next check. The final role brief carries its own packet reference and names cross-functional handoffs as requested evidence; a handoff is never an observed fact or human approval.

The top-level `response_service.enabled` declaration is outside the Run DAG. Core keeps one bounded response service available for the stable Job before its first Run and between Runs. It combines sanitized role, safe configuration, lifecycle, latest-Run context, and Job-scoped playbook RAG without starting work, discovering peers, publishing an exchange, or exposing confidential run artifacts.


## Acceptance criteria

- The source manifest expands and validates.
- Exactly one route-neutral agent executes both declared steps.
- The focused synthetic fixture produces a durable final artifact.
- The aspect packet contains evidence, assumptions, confidence, risks, approvals, and next-check fields.
- Response context excludes credentials, contact details, document bodies, and other confidential run artifacts.
- The final artifact states that consequential external actions remain approval-required.
The final role brief identifies all four cross-functional handoffs and keeps each evidence dependency explicit.
