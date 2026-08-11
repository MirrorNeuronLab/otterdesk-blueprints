# OtterDesk Conversation Assistant

`otterdesk_conversation_assistant` is a private system co-worker used by the
OtterDesk desktop app. It turns a user question plus a bounded, identity-checked,
read-only MCP snapshot from a hired co-worker into a grounded conversational
reply.

The desktop app installs this blueprint on first startup after the MirrorNeuron
runtime becomes available. It is deliberately absent from the Co-worker Hub and
My Team: it is runtime infrastructure for supervising other co-workers, not a
co-worker the user hires directly.

The workflow never discovers MCP endpoints, accepts credentials, sends messages,
or mutates the target job. Endpoint discovery, service identity validation, tool
allowlisting, response bounds, and MCP reads remain owned by the Electron main
process. This blueprint receives only the resulting snapshot.

## Workflow

1. `prepare_conversation_context` validates the request, target identity, and
   read-only MCP marker and writes a bounded internal context artifact.
2. `answer_desktop_conversation` uses the MirrorNeuron actor LLM selected by the
   runtime to answer from that artifact and writes `final_artifact.json`.

Normal desktop runs require a live runtime-selected LLM. Quick tests use a
deterministic fallback and make no network calls.

