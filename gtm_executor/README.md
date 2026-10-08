# GTM executor

A long-running Bibblio marketing co-worker. Shared goal: market Bibblio through
relevant, human-approved email outreach. Use this with `gtm_planner`.

## Setup and operation

Hire co-workers through MirrorNeuron's catalog and blueprint-add API. In
OtterDesk’s Collaboration tab, enable a board, add compatible co-workers, and
save a shared goal. The catalog declares groups of up to five planner/executor
instances. Each receives the board identity and every other member’s stable Job
ID and blueprint role. Configure websites and private inputs separately. Keep
all members on the same local runtime: their read-only MCP exchanges bind to
loopback. Saving a board does not start work; use each co-worker’s existing
lifecycle controls explicitly. Existing scalar-peer pairs keep their runtime
configuration until their membership or shared goal is edited.

The planner reads public Bibblio product evidence at startup and at most daily,
extracts exact source quotations, and proposes one idea per day or changed
instruction. A human approves the idea before its MCP handoff. The executor
polls AgentMail every 60 seconds, drafts emails and replies, and requires a
second approval of exact sender, copy, and recipients before delivery.
Use Configure > Marketing instructions to provide a new task or corrected brief.
Chat describes the role and workflow; it does not authorize sending.

## Contacts and email

Executor CSV columns, in order: `Name,Email,Category,Note,Highlight`. Contact
records remain private to the executor. Malformed addresses are quarantined;
category and note values are unverified hints. `other` is proposed for education
partner review, not treated as verified occupation. Newsletter eligibility is
false until a supervisor confirms subscription status.

Initial campaigns contain at most 25 recipients. Each receives a separate email.
Email copy is rendered into one escaped Bibblio HTML template plus plain text.
Approvals expire after 48 hours. A changed sender, recipient, or draft needs new
review. No scheduling, automatic follow-up, cold-contact enrichment, child
profiling, or automatic reply sending is enabled.

Only the executor receives `AGENTMAIL_API_KEY`, injected from OtterDesk's
encrypted credential store. Configure the provisioned AgentMail inbox ID.
Never put a key or real contacts into source, example files, or config JSON.
The checked-in CSV is synthetic and cannot be used for live delivery.

## Reliability and privacy

Core interactions are the approval authority. Peer MCP data and replicated
files cannot grant approval. The SDK read-only exchange publishes only campaign
briefs, segment counts, and aggregate results. Contact addresses, incoming mail,
and credentials are excluded from the planner and response-service knowledge.
The executor's Job-scoped SQLite database retains campaigns, quarantine,
suppression, inbox cursors, draft IDs, send claims, and receipts across restarts.
Drafts never receive AgentMail `send_at`. Provider rate/transport failures back
off; ambiguous sends stop and require operator reconciliation, never automatic
resend. An accepted message is not proof of inbox delivery or business results.

## Validation

Run `python -m pytest tests/test_gtm_services.py -q` from the catalog repository
with the declared sibling SDK, agents, and skills available. The suite uses
synthetic data, mocked AgentMail/models, and an isolated real MCP stdio exchange.
Live provider sending is not a setup or test prerequisite.

## Context engine contract

The `mn.context` descriptor explicitly disables Membrane runtime recall for this blueprint: its payload does not call TextMemory. Existing domain knowledge/RAG, live status, MCP controls, and Core coordination retain their own contracts. The retired conversation-memory declaration is removed, so this workflow does not start a context compressor or require a Membrane SDK merely to launch. Any future runtime-memory consumer must declare `mirrorneuron-python-sdk[context]`, ingest complete preprocessed text under trusted job/run scope, and use the Markdown/DuckDB CPU service.

## Shared capability ownership

Core-authoritative nonblocking approvals and verified peer discovery/cursors use shared SDK helpers. Marketing approval triggers, allowed marketing roles and work-packet content remain blueprint-owned.
Group packets carry the board identity and exact member list. Each peer keeps
an independent cursor; a peer restart resets only that cursor. Packets from
another board or membership are rejected before consumption. Peer data never
grants approval, and each executor still requires review of its exact delivery.
