# OtterDesk Conversation Assistant Specification

## Identity

- Blueprint id: `otterdesk_conversation_assistant`
- Workflow id: `otterdesk_conversation_assistant_v1`
- Lifecycle: bounded batch run on a stable internal MN job
- Visibility: internal to OtterDesk

## Input contract

The `inputs.payload` object must contain:

- `schema_version`: `otterdesk.conversation_assistant.request.v1`
- `request_id`: opaque desktop-generated request id
- `question`: non-empty user question, at most 20,000 characters
- `conversation_history`: up to eight bounded recent user/co-worker turns for continuity; never evidence
- `target_worker`: bounded worker, mission, blueprint, stable job, and runtime run identity
- `mcp_context`: `otterdesk.worker_mcp_conversation_context.v1` with
  `mcp.readOnly` set to `true` and identity matching the target
- `supervision_context`: `otterdesk.worker_supervision_context.v1` with the
  identity-matched runtime summary and editable non-secret configuration fields

The payload must not contain MCP URLs, tokens, passwords, or renderer-provided
shell/filesystem instructions.

The model prompt receives at most twelve compact job records selected from the
bounded snapshot by recency and question relevance. Configuration fields are
included only when the question asks about changing settings. This keeps normal
job conversation responsive without weakening the read-only identity checks.

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
