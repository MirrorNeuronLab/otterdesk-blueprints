# Growth & Partnerships Co-worker v2 Specification

## Purpose

Own demand discovery, contact qualification, channel experiments, partnerships, draft outreach, and a bounded development-only SMTP delivery check for a configurable business and goal. The default demo business is Bibblio and its default goal is "Build a successful business for Bibblio."

## Independence contract

The blueprint declares exactly one domain specialist and three sequential steps: qualify_seed_contacts, publish_gtm_outreach_queue, and deliver_approved_email. It produces its own final artifact and does not depend on any peer blueprint to complete. The final step is also the only external side-effect boundary and has one attempt with no automatic retry.

## Durable work-packet and response contract

Each run writes durable `mn.goal.work_packet.v1` records with its stable goal, role, stage, source references, observed facts, assumptions, recommendation, confidence, risks, requested approvals, outputs, and next check. The final role brief carries its own packet reference and names cross-functional handoffs as requested evidence; a handoff is never an observed fact or human approval.

The top-level `response_service.enabled` declaration is outside the Run DAG. Core keeps one bounded response service available for the stable Job before its first Run and between Runs. It combines sanitized role, safe configuration, lifecycle, latest-Run context, and Job-scoped playbook RAG without starting work, discovering peers, publishing an exchange, or exposing confidential run artifacts.


## Acceptance criteria

- The source manifest expands and validates.
- Exactly one route-neutral agent executes all three declared steps.
- The reusable email-delivery skill validates the allowlisted TLS endpoint and returns credential-free errors.
- The default run sends no email and requires no SMTP credentials.
- Development mode cannot connect without explicit approval and all secret environment values.
- Development mode sends one message to the environment-injected test recipient even when the queue contains many contacts.
- Replaying a completed delivery returns the stored receipt without opening a second SMTP connection.
- The focused synthetic fixture produces a durable final artifact.
- The aspect packet contains evidence, assumptions, confidence, risks, approvals, and next-check fields.
- Response context excludes credentials, contact details, document bodies, and other confidential run artifacts.
- The final artifact accurately distinguishes no-send and one-message development-delivery outcomes while keeping production actions approval-required.
The final role brief identifies all four cross-functional handoffs and keeps each evidence dependency explicit.
