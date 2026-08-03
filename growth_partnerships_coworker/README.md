# Growth & Partnerships Co-worker

Blueprint ID: growth_partnerships_coworker

Default demo business: Bibblio.

Default demo goal: Build a successful business for Bibblio.

The role is generic. Set `business_name`, `business_goal`, `goal_id`, and
`planning_horizon_days` for another business; the bundled knowledge and sample
inputs remain an unchanged Bibblio demonstration.

This is one independent member of the `business-success-team` collaboration group. It owns demand discovery, contact qualification, channel experiments, partnerships, draft outreach, and a development-only SMTP delivery check. It can run by itself and exchange bounded aggregate goal packets with explicitly approved peer co-workers.

## Workflow

1. qualify_seed_contacts creates the aspect analysis and a durable work packet.
2. publish_gtm_outreach_queue publishes a staged, approval-ready queue packet.
3. deliver_approved_email writes the final packet. It sends nothing by default; when explicitly enabled and approved, it performs one development SMTP delivery to the environment-injected test recipient.

Input: an approved adult-professional contact CSV with Name, Email, Category, Note, and Highlight columns.

Local working artifact: confidential_outreach_queue.json.
Local delivery artifact when SMTP is attempted: `confidential_email_delivery_receipt.json`.
Final role brief: `growth_partnerships_packet.json` and `final_artifact.json`.

## Founder-facing output

The role brief contains a demand scorecard, decisions for the founder, a 90-day
pilot plan, and named handoffs: Finance supplies CAC/payback limits; Lifecycle
supplies retained-customer evidence; Quality & Safety supplies claim boundaries;
and Content Studio supplies approved proof assets.

## SMTP development check

SMTP is disabled by default. Production and bulk-list delivery are not implemented. To run one reviewed development check, keep the credential values outside the repository and inject:

```bash
export MN_SMTP_USERNAME="<full iCloud mail address>"
read -s MN_SMTP_PASSWORD
export MN_SMTP_PASSWORD
export MN_SMTP_DEV_RECIPIENT="<single approved test inbox>"
```

In an uncommitted `config/overwrite.json`, set `smtp_delivery.enabled` to `true` and provide `inputs.payload.email_send_approval` with `approved: true` and a unique, bounded `approval_id`. The worker uses `smtp.mail.me.com:587` with STARTTLS. It ignores all queued addresses, removes the queued contact greeting, prefixes the subject with `[Development test]`, sends exactly one message, and never retries the SMTP transaction.

Names, email addresses, source notes, individual drafts, credentials, and the development recipient stay out of MCP packets. The local receipt contains bounded delivery metadata but no address, username, or password. An interrupted SMTP attempt is treated as indeterminate and must be reviewed in a new run rather than retried.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/edtech_contacts_sample.csv, keeps SMTP disabled, and records `email_send_approval.approved: false`. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run growth_partnerships_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-business-success.

While a run is active, the blueprint starts a loopback, read-only
`mn-job-collaboration` MCP service on a runtime-allocated port. OtterDesk and
approved same-node peer jobs can use that endpoint to read bounded progress and
work-packet updates; stopping the run removes the endpoint.

See SPEC.md and payloads/knowledge/gtm_playbook.md for the role contract.
