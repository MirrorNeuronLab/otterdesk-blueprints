# GTM Assistant v1 Specification

## Purpose

Own activation, retention, support friction, voice-of-customer synthesis, and draft lifecycle interventions for a configurable business and goal. The unchanged Bibblio demo uses synthetic parent-feedback inputs and a bundled lifecycle playbook.

## Run contract

The Run DAG declares one lifecycle specialist plus an optional read-only development reply monitor. It diagnoses the customer journey, writes a lifecycle packet, optionally performs one explicitly approved development rendering check, and monitors matching reply headers only when monitoring is enabled. A disabled monitor returns immediately; a Run is never kept alive to serve chat or MCP.

Each analytical step writes a durable `mn.goal.work_packet.v1` record containing stable goal, role, stage, sources, observed facts, assumptions, modeled analysis, recommendation, confidence, risks, approvals, outputs, and next-check fields. The final result carries the useful packet reference and unresolved cross-functional evidence requests in `job_context`. It does not publish an exchange database, discover peers, or treat handoffs as observed evidence or approval.

## Real-time response contract

The top-level `response_service.enabled` declaration is outside the DAG. Core owns one always-warm responder per stable Job, including before the first Run and between Runs. The responder uses the shared default LLM plus Job-scoped RAG over `payloads/knowledge/parent_lifecycle_playbook.md` to answer bounded questions about purpose, status, progress, published results, and missing evidence. Asking a question never creates or keeps alive a Run.

The response service and Run workers use the same Job-scoped RAG owner. Context excludes credentials, raw logs, internal paths, unrestricted artifacts, email addresses, and message bodies. If model or RAG access is degraded, the service returns a deterministic grounded status summary with warnings.

## Input and evidence contract

Input is a de-identified customer-feedback CSV. Synthetic fixtures are labeled `synthetic_demo`; user data is confidential by default. Missing evidence remains explicit and cannot be converted into an observed claim. Actor-assisted analysis resolves MirrorNeuron's logical `default` model rather than pinning a machine-specific endpoint.

## Safety and approval contract

Customer communications, copy, cohorts, frequency caps, and support escalation rules require approval. The optional SMTP check may send one aggregate draft to an environment-injected development inbox only after explicit approval. It uses no customer address or customer-specific data, records a confidential receipt, and never authorizes production messaging. The optional IMAP monitor reads only matching unread headers, marks nothing read, persists no body text, and sends no reply.

## Acceptance criteria

- The source manifest expands with `response_service` preserved outside workflow, agents, and services.
- The legacy run-scoped MCP node, exchange artifact, peer inputs, and MCP dependencies are absent.
- The lifecycle playbook is seeded as Job knowledge and indexed by the Job-scoped RAG owner.
- A never-run Job can answer grounded MCP questions without changing `run_count`.
- Disabled reply monitoring terminates immediately; enabled monitoring starts only after the approved development send.
- The final artifact preserves goal-work-packet context and names unresolved evidence without fabricating peer conclusions.
- Development delivery remains disabled by default, requires an approval ID plus secret-injected SMTP values, and sends at most one test message per Run.
- Response and monitoring projections expose no credentials, addresses, message content, internal endpoint, or path.

## Prototype limits

This is an evidence-bounded lifecycle planning assistant, not authorization to contact customers or make legal, privacy, child-safety, educational, financial, brand, or accessibility decisions.
