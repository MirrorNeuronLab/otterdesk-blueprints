# GTM Assistant

Blueprint ID: gtm_assistant

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns activation, retention, support friction, voice-of-customer synthesis, and draft lifecycle interventions. It can run by itself and exchange bounded aggregate goal packets with explicitly approved peer co-workers.

## Workflow

1. diagnose_customer_journey creates the aspect analysis and a durable work packet.
2. publish_customer_lifecycle_packet publishes a final, approval-ready aspect packet.
3. deliver_approved_lifecycle_email evaluates an optional, one-recipient development SMTP rendering check.

Input: a de-identified customer-feedback CSV. The unchanged bundled demo uses parent feedback.

Local working artifact: draft_customer_interventions.json.
Final role brief: `customer_lifecycle_packet.json` and `final_artifact.json`.

## Founder-facing output

The role brief contains an activation/retention scorecard, founder decisions, a
90-day cohort plan, and named handoffs linking Finance targets, Growth promises,
Content gaps, and Quality & Safety claim and escalation boundaries.

## Control boundary

It does not contact customers. Copy, cohorts, frequency caps, and support escalation rules require approval, and raw customer records are not shared through MCP. The only supported delivery is an explicitly approved, one-recipient development test using an environment-injected inbox; it never uses a customer address or customer-specific data and does not authorize production messaging.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/parent_feedback.csv. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run gtm_assistant

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-business-success.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

## Development SMTP check

SMTP is disabled by default. An operator may enable only the development
delivery configuration and provide `email_send_approval` with
`approved: true` plus a bounded `approval_id`. The worker also requires exactly
one environment-injected test recipient and SMTP credentials through
`MN_SMTP_DEV_RECIPIENT`, `MN_SMTP_USERNAME`, and `MN_SMTP_PASSWORD`.

The check sends one aggregate rendering draft at most once per run through the
allowlisted iCloud STARTTLS endpoint. It uses neither a customer address nor
customer-specific data. Its MCP record and final brief expose only delivery
status and recipient count; the confidential receipt excludes credentials,
addresses, and approval text.

OtterDesk presents an explicit development-delivery switch plus separate fields
for `smtp.mail.me.com`, port `587`, `starttls`, the iCloud sender/SMTP username,
an Apple app-specific password, and the single development recipient. The
password remains in the OS
credential store. The desktop sends the three identity/credential values over
the authenticated local launch API as declared secret environment values; they
are not included in the blueprint configuration overlay. IMAP
`imap.mail.me.com:993` is an incoming-mail setting and cannot be used for this
outbound-only check.

See SPEC.md and payloads/knowledge/parent_lifecycle_playbook.md for the role contract.
