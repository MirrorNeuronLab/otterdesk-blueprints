# GTM Assistant

Blueprint ID: gtm_assistant

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` group. It owns activation, retention, support friction, voice-of-customer synthesis, and draft lifecycle interventions. It runs independently and records its durable goal work packet as ordinary result context.

Actor-assisted analysis uses MirrorNeuron's logical `default` model. Operators
can change that shared default with `mn model add --file <definition.json>
--default` without editing or reinstalling a machine-specific model name in
this blueprint.

## Workflow

1. diagnose_customer_journey creates the aspect analysis and a durable work packet.
2. publish_customer_lifecycle_packet publishes a final, approval-ready aspect packet.
3. deliver_approved_lifecycle_email evaluates an optional, one-recipient development SMTP rendering check.
4. monitor_development_email_replies keeps the approved run active until manually stopped and reads only matching reply headers from the configured development inbox.

Input: a de-identified customer-feedback CSV. The unchanged bundled demo uses parent feedback.

Local working artifact: draft_customer_interventions.json.
Final role brief: `customer_lifecycle_packet.json` and `final_artifact.json`.

## Founder-facing output

The role brief contains an activation/retention scorecard, founder decisions, a
90-day cohort plan, and named handoffs linking Finance targets, Growth promises,
Content gaps, and Quality & Safety claim and escalation boundaries.

## Control boundary

It does not contact customers. Copy, cohorts, frequency caps, and support escalation rules require approval. The only supported delivery is an explicitly approved, one-recipient development test using an environment-injected inbox; it never uses a customer address or customer-specific data and does not authorize production messaging. The optional reply monitor is read-only: it never sends a reply, retains no message body, and counts only replies from that same development inbox that reference the development message.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/parent_feedback.csv. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run gtm_assistant

## Real-time Job questions

The stable Job owns one response service outside the Run DAG. It stays available
before the first Run and between Runs, uses the bundled lifecycle playbook as
Job-scoped RAG knowledge, and answers bounded questions about purpose, status,
progress, results, and missing evidence. Asking a question never creates a Run
or starts the reply monitor. The legacy run-scoped MCP node, peer inputs, and
exchange database are not part of this blueprint.

## Development SMTP check

SMTP is disabled by default. An operator may enable only the development
delivery configuration and provide `email_send_approval` with
`approved: true` plus a bounded `approval_id`. The worker also requires exactly
one environment-injected test recipient and SMTP credentials through
`MN_SMTP_DEV_RECIPIENT`, `MN_SMTP_USERNAME`, and `MN_SMTP_PASSWORD`.

The check sends one aggregate rendering draft at most once per service run through the
allowlisted iCloud STARTTLS endpoint. It uses neither a customer address nor
customer-specific data. Its final brief exposes only delivery status and
recipient count; the confidential receipt excludes credentials,
addresses, and approval text.

OtterDesk presents an explicit development-delivery switch plus separate fields
for `smtp.mail.me.com`, port `587`, `starttls`, the iCloud sender/SMTP username,
an Apple app-specific password, and the single development recipient. The
password remains in the OS
credential store. The desktop sends the three identity/credential values over
the authenticated local launch API as declared secret environment values; they
are not included in the blueprint configuration overlay. When explicitly
enabled after the approved send, the same identity is used with
`imap.mail.me.com:993` over SSL to inspect unread message headers only. A reply
counts only when its sender is the configured development recipient and its
`In-Reply-To` or `References` header names the development message. No message
is marked read, no message content is stored, and no reply is sent.

See SPEC.md and payloads/knowledge/parent_lifecycle_playbook.md for the role contract.
