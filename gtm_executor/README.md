# GTM executor

A long-running Bibblio marketing co-worker. Shared goal: market Bibblio through
relevant, human-approved email outreach. Use this with `gtm_planner`.

## Setup and operation

Hire both through MirrorNeuron's catalog and blueprint-add API. Use OtterDesk’s Collaboration tab to select the pair and edit their common
goal. The desktop binds stable partner Job IDs and the `bibblio-marketing`
exchange identity. Configure each co-worker’s website and private inputs separately. Keep
both on the same local runtime: their read-only MCP exchanges bind to loopback.
This version does not support placing the pair on different computers.
Saving configuration does not start work. Choose Start now explicitly for both;
pause or stop with OtterDesk's existing lifecycle controls.

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
