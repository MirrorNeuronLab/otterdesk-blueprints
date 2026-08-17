# OtterDesk Conversation Assistant Specification

## Identity

- Blueprint id: `otterdesk_conversation_assistant`
- Workflow id: `otterdesk_conversation_assistant_v1`
- Lifecycle: bounded batch run on a stable internal MN job
- Visibility: internal to OtterDesk

## Input contract

The `inputs.payload` object must contain:

- `schema_version`: `otterdesk.conversation_assistant.request.v2`
- `request_id`: opaque desktop-generated request id
- `question`: non-empty user question, at most 20,000 characters
- `conversation_history`: up to eight bounded recent user/co-worker turns for continuity; never evidence
- `target_worker`: bounded worker, mission, blueprint, stable job, and runtime run identity
- `mcp_context`: `otterdesk.worker_stable_job_mcp_context.v1` with
  `mcp.readOnly` set to `true` and identity matching the target
- `supervision_context`: `otterdesk.worker_supervision_context.v1` with the
  identity-matched runtime summary and editable non-secret configuration fields

The payload must not contain MCP URLs, tokens, passwords, or renderer-provided
shell/filesystem instructions.

The stable job and blueprint identities are always required. Run identity is
required only when a latest run exists; a never-run co-worker legitimately has
no run id and remains conversational.

The model prompts receive at most twelve compact job records selected from the
bounded snapshot by recency and question relevance. Configuration fields are
included only when the question asks about changing settings. This keeps normal
job conversation responsive without weakening the read-only identity checks.

Live runs request the logical `default` runtime model. MirrorNeuron owns
hardware-aware concrete model selection and preparation, and inference uses the
selected node's LiteLLM gateway; the blueprint does not hard-code a model
artifact or direct provider endpoint.

After deterministic identity and bounds validation, a default-LLM co-worker
proxy classifies the turn as conversation, monitoring, or control and drafts an
accountable first-person response. A separate default-LLM assistant pass treats
that draft as untrusted, verifies it against the same evidence and supervision
state, and produces the final reply. Both agents request the logical `default`
model; neither uses a desktop database-response shortcut.

Each live model turn has a 1,200-token budget. The prompt limits ordinary
replies to 1,200 characters, six evidence ids, and at most three proposed
configuration changes.

If either selected model turn returns malformed JSON, that step makes one
tighter JSON-only retry. A second formatting-only failure uses the deterministic
grounded fallback from the same bounded snapshot; transport, authentication,
model-selection, and other runtime errors still fail rather than being masked.

## Output contract

`final_artifact.json` has type `otterdesk_conversation_reply` and contains the
request id, target identity, grounded reply, source record ids, the MCP revision,
and LLM usage metadata. It may also contain a configuration proposal limited to
the desktop-supplied non-secret editable fields. The reply must distinguish
staged evidence from final evidence and say when the snapshot does not answer
the question.

## Safety boundary

This co-worker is read-only. It cannot call target MCP tools, respond to human
approval requests, send external communications, alter schedules, start or stop
jobs, access arbitrary files, or execute commands. It can only propose a
configuration change; OtterDesk independently validates that proposal and a
human must click Apply before anything is saved. Consequential actions remain in
the target co-worker's own approval and runtime contracts.
