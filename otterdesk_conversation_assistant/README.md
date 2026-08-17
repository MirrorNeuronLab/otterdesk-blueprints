# OtterDesk Conversation Assistant

`otterdesk_conversation_assistant` is a private system co-worker used by the
OtterDesk desktop app. It turns a user question plus a bounded, identity-checked,
read-only MCP snapshot from a hired co-worker into a grounded conversational
reply.

The desktop app installs this blueprint on first startup after the MirrorNeuron
runtime becomes available. It is deliberately absent from the Co-worker Hub and
My Team: it is runtime infrastructure for supervising other co-workers, not a
co-worker the user hires directly.

The workflow never constructs MCP endpoints, accepts credentials, sends
messages, or mutates the target job. Stable endpoint construction, API
authentication, identity validation, tool allowlisting, response bounds, and
MCP reads remain owned by the Electron main process. This blueprint receives
only the resulting `otterdesk.worker_stable_job_mcp_context.v1` snapshot.

## Workflow

1. `prepare_conversation_context` validates the request, target identity, and
   read-only MCP marker and writes a bounded internal context artifact.
2. `draft_coworker_turn` uses the runtime-selected default LLM to interpret the
   supervisor's conversational, monitoring, or control intent and draft a turn
   in the accountable target co-worker's voice.
3. `answer_desktop_conversation` uses a separate default-LLM turn to verify the
   draft against the same evidence and safety boundaries, then writes
   `final_artifact.json`.

Normal desktop runs request the logical `default` LLM. MirrorNeuron selects and
prepares the operator-configured concrete model for the execution node, then the
actor calls it through that node's LiteLLM gateway. Every normal chat
turn—including greetings, status checks,
monitoring questions, and configuration requests—uses both model passes rather
than a desktop database-response shortcut. Quick tests use deterministic
fallbacks and make no network calls. Live replies use compact JSON contracts
and a 1,200-token allowance per model turn. A malformed JSON response gets one
stricter retry and then a bounded deterministic snapshot reply, so formatting
variance does not turn a safe read-only chat into a 500.
