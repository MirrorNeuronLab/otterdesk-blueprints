# Growth & Partnerships Co-worker v2 Specification

## Purpose

Own demand discovery, contact qualification, channel experiments, partnerships, draft outreach, and a bounded development-only SMTP delivery check for a configurable business and goal. The default demo business is Bibblio and its default goal is "Build a successful business for Bibblio."

## Independence contract

The blueprint declares exactly one domain specialist and three sequential steps: qualify_seed_contacts, publish_gtm_outreach_queue, and deliver_approved_email. It produces its own final artifact and does not depend on any peer blueprint to complete. The final step is also the only external side-effect boundary and has one attempt with no automatic retry.

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

Input is an approved adult-professional contact CSV with Name, Email, Category, Note, and Highlight columns. Synthetic fixtures are labeled synthetic_demo. User-supplied data is treated as confidential unless an operator explicitly classifies a derived aggregate otherwise. Missing evidence remains explicit and cannot be converted into an observed claim.

## SMTP, safety, and approval contract

SMTP is disabled by default and only development mode is supported. A delivery requires both `smtp_delivery.enabled: true` and an input `email_send_approval` object containing `approved: true` and a bounded `approval_id`. Missing configuration or approval sends nothing.

The worker accepts only `smtp.mail.me.com:587` with STARTTLS. Username and app-specific password come from `MN_SMTP_USERNAME` and `MN_SMTP_PASSWORD`; the single development recipient comes from `MN_SMTP_DEV_RECIPIENT`. No committed file contains these values. Development mode ignores all queued addresses, strips the queued contact greeting from the selected quality-approved draft, sends exactly one message, and never uses CC or BCC.

Before connecting, the blueprint writes a confidential run-local reservation. A completed receipt makes replay idempotent; any prior incomplete or failed attempt causes the run to fail closed because SMTP cannot prove exactly-once delivery after interruption. Production and bulk-list delivery are out of scope.

Names, email addresses, source notes, individual drafts, credentials, and the development test recipient stay out of MCP packets and final artifacts. The confidential local delivery receipt contains only bounded status, message identity, policy, and approval-reference metadata.

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
- MCP exchange publication contains no credentials or forbidden private fields.
- The final artifact accurately distinguishes no-send and one-message development-delivery outcomes while keeping production actions approval-required.
- The final role brief identifies all four peer-role handoffs and preserves bounded peer evidence when configured.
