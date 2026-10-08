# GTM executor specification

`gtm_executor` is a blueprint/v1 service with one supervised logical step and a
runtime-owned, read-only `mn-job-collaboration` MCP auxiliary service. Each hire
owns one stable Job, Job storage, and one long-lived execution until stopped.

## Interfaces and ownership

Role documents own identity, dependencies, service bindings, setup, input, output,
and response-service contracts. The main input values are website_url, goal_id,
collaboration_group_id, collaboration_peers, common_goal, and instruction.
peer_job_id is retained only for existing scalar-peer pairs. Executor additionally owns contacts_file,
inbox_id, and newsletter_eligible. Credentials are process-only environment.

Domain modules own research/planning or contacts/drafting/inbox/delivery policy.
Step modules contain only StepSpec contracts. Agent modules bind the specialist.
The existing supervised-service package handles termination and cycle timing.
Runtime context and MCP startup do not perform marketing work. HostLocal workers
keep the MCP group on the local runtime with loopback-only endpoints.

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

## Context engine contract

The `mn.context` descriptor explicitly disables Membrane runtime recall for this blueprint: its payload does not call TextMemory. Existing domain knowledge/RAG, live status, MCP controls, and Core coordination retain their own contracts. The retired conversation-memory declaration is removed, so this workflow does not start a context compressor or require a Membrane SDK merely to launch. Any future runtime-memory consumer must declare `mirrorneuron-python-sdk[context]`, ingest complete preprocessed text under trusted job/run scope, and use the Markdown/DuckDB CPU service.

## Shared capability ownership

Core-authoritative nonblocking approvals and verified peer discovery/cursors use shared SDK helpers. Marketing approval triggers, allowed marketing roles and work-packet content remain blueprint-owned.

The product declares `mn.collaboration.group.v1`, capacity five, mutual planner/
executor compatibility, and structured peers (`jobId`, `blueprintId`). Every
published group packet carries a group ID and the complete sorted stable-Job
membership. The SDK verifies Core identity, blueprint role, goal, group, and
membership before returning packets. Independent execution/revision cursors
are stored under the group ID; restarting a peer does not reset other peers.
Only approved-brief packets initiate executor drafting, with idempotency scoped
to publisher and packet ID. Final email approval remains mandatory. Existing
pairs read the legacy scalar peer until an explicit board change upgrades them.
