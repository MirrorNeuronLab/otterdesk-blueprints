# GTM planner specification

`gtm_planner` is a blueprint/v1 service with one supervised logical step and a
runtime-owned, read-only `mn-job-collaboration` MCP auxiliary service. Each hire
owns one stable Job, Job storage, and one long-lived execution until stopped.

## Interfaces and ownership

Role documents own identity, dependencies, service bindings, setup, input, output,
and response-service contracts. The main input values are website_url, goal_id,
peer_job_id, and instruction. Executor additionally owns contacts_file,
inbox_id, and newsletter_eligible. Credentials are process-only environment.

Domain modules own research/planning or contacts/drafting/inbox/delivery policy.
Step modules contain only StepSpec contracts. Agent modules bind the specialist.
The existing supervised-service package handles termination and cycle timing.
Runtime context and MCP startup do not perform marketing work. HostLocal workers
keep the MCP pair on the local runtime with loopback-only endpoints.

## Review state

Planner: evidence -> proposed idea -> pending human review -> approved/rejected/
expired. Approved ideas become versioned goal work packets. Executor: handoff or
human instruction -> immutable draft and recipient snapshot -> pending final
review -> approved/rejected/expired -> per-recipient sending -> sent or needs
review. A durable unique send claim precedes the provider mutation. Uncertain
outcomes never automatically retry. Replaying work packets is idempotent.

Core owns human interaction receipts. Approval request identities bind content
revisions; peer packets are input data only. Receipt expiry, exact remote-draft
comparison, suppression, stop state, and the configured sender are checked at
the delivery boundary. Campaign revision or sender changes cannot reuse approval.

## Data and failures

Persistent state belongs under the SDK-provided Job data directory. Public status
is the bounded `marketing_status.json` artifact, with generic errors rather than
private text or transport bodies. Missing models, browser evidence, runtime,
credentials, or peers must not fabricate successful work. Missing peers are
reported while independent role work continues. Ambiguous peer identity blocks
handoffs. Malformed content and overlarge approval previews fail before sending.

The response-service knowledge contains only role guidance. Contact lists and
inbound mail are never indexed. Source facts are exact public quotations with
URLs; planned metrics are not reported as observed performance.
