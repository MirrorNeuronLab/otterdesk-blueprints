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
- `target_worker`: bounded worker, blueprint, stable job, and runtime run identity
- `mcp_context`: `otterdesk.worker_mcp_conversation_context.v1` with
  `mcp.readOnly` set to `true` and identity matching the target

The payload must not contain MCP URLs, tokens, passwords, or renderer-provided
shell/filesystem instructions.

## Output contract

`final_artifact.json` has type `otterdesk_conversation_reply` and contains the
request id, target identity, grounded reply, source record ids, the MCP revision,
and LLM usage metadata. The reply must distinguish staged evidence from final
evidence and say when the snapshot does not answer the question.

## Safety boundary

This co-worker is read-only. It cannot call target MCP tools, respond to human
approval requests, send external communications, alter schedules, start or stop
jobs, access arbitrary files, or execute commands. Consequential actions remain
in the target co-worker's own approval and runtime contracts.

