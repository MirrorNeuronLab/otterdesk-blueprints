# {{BLUEPRINT_NAME}} user manual

This co-worker is a no-op starter. It has no domain mission yet.
Starting a run executes one bounded empty step and completes it. It needs no
inputs or GPU and produces no domain artifacts; runtime receipts remain local
to the configured runtime storage.

Use the standard MCP supervision tools to inspect status and control a run.
Asking a Chat question does not start work; conversation uses the runtime's
configured response model. Workflow execution does not call a model.

Replace the domain hook and document its inputs, outputs, permissions,
evidence and limits before offering this co-worker for real work.
