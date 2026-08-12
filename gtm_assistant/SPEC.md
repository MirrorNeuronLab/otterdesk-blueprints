# GTM Assistant v1 Specification

## Purpose

Own activation, retention, support friction, voice-of-customer synthesis, and draft lifecycle interventions for a configurable business and goal. After an explicitly approved development-only send, it can remain active as a manually stopped service that reports matching test-inbox replies through MCP. The unchanged default Bibblio demo uses parent-feedback inputs.

## Independence contract

The blueprint declares one domain specialist plus a read-only development reply monitor. It diagnoses the customer journey, publishes a lifecycle packet, optionally sends one explicitly approved development rendering check, then keeps the service active only when the optional reply monitor is enabled. It produces its own final artifact and does not depend on any peer blueprint to complete.

## Collaboration contract

The co-worker writes mirrorneuron.collaboration.goal-work-packet records with a stable goal_id, role and stage identity, source references, observed facts, assumptions, modeled analysis, recommendation, confidence, risks, requested approvals, outputs, and next check. MCP publication is job-scoped and bounded to the run directory. Peer reads are disabled by default and use only explicitly configured servers.

The final lifecycle-packet step re-reads bounded peer packets and carries them into a founder-facing
role brief. That brief must include `role_contribution`, `north_star_question`,
`role_scorecard`, `founder_decisions`, `ninety_day_plan`, and
`cross_functional_handoffs`. With no peer packets, it explicitly reports the
evidence dependencies that remain unresolved; a peer recommendation never counts
as human approval.

MCP does not select peers, route work, retry steps, decide completion, or approve actions.
Each active run also supervises a loopback `mn-job-collaboration` service with
the `mcp` and `job-collaboration` tags. It publishes bounded staged status
transitions and existing staged/final work packets for OtterDesk and explicitly
approved same-node peers. The service is read-only. When development reply
monitoring is enabled after a successful approved send, it remains available
until manually stopped and reports only reply counts and monitor status; it
never exposes message bodies, addresses, or reply content through MCP.

## Input and evidence contract

Input is a de-identified customer-feedback CSV; the bundled demo uses parent feedback. Synthetic fixtures are labeled synthetic_demo. User-supplied data is treated as confidential unless an operator explicitly classifies a derived aggregate otherwise. Missing evidence remains explicit and cannot be converted into an observed claim.

## Safety and approval contract

It does not contact customers. Copy, cohorts, frequency caps, and support escalation rules require approval, and raw customer records are not shared through MCP. An opt-in development-only SMTP check may render one aggregate draft to an environment-injected test inbox only after explicit approval; it uses no customer address or customer-specific data, records a confidential receipt, and never authorizes production messaging. An optional IMAP monitor may inspect only unread headers from that same test inbox when they reference the development message; it does not mark mail read, persist body text, or send a reply.

## Acceptance criteria

- The source manifest expands and validates.
- The lifecycle specialist owns its three bounded workflow steps; a dedicated read-only service agent owns reply monitoring.
- The focused synthetic fixture produces a durable final artifact.
- The aspect packet contains evidence, assumptions, confidence, risks, approvals, and next-check fields.
- MCP exchange publication contains no credentials or forbidden private fields.
- The final artifact states that consequential external actions remain approval-required.
- The final role brief identifies all four peer-role handoffs and preserves bounded peer evidence when configured.
- A development SMTP check is disabled by default, requires an approval id plus secret-injected SMTP values, and can send at most one test email per service run.
- Reply monitoring is disabled by default, remains active only after the approved send, and publishes no message content or address through MCP.
