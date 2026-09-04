# Runtime DAG Flow Patterns

Every catalog blueprint is submitted to MirrorNeuron Core as `flow.steps` and
`flow.graph.edges`. The source-manifest compiler derives those fields from a
step's `requires` and `provides` contracts, or uses explicit `workflow.edges`
when a custom event route is required. `trigger_rule` is evaluated by the Core
workflow ledger, not only displayed in the UI.

## Patterns in this catalog

| Blueprint | Runtime flow pattern |
| --- | --- |
| CCTV Operator | Event-driven service flow: monitor ingress, sample frames, detect, and report. |
| Drug Discovery Research Assistant | Bounded discovery batch: one cycle evaluates five distinct molecules, then review and reporting complete the run. |
| Financial Advisor | Ordered regulated-state pipeline: packet intake, household analysis, tax review, portfolio risk, public guidance, reconciliation, and publication. |
| Legal Assistant | Fork/join: document reading fans out to invoice and contract review lanes; evidence reconciliation waits for both. |
| Purchasing Manager | Ordered procurement pipeline: requirements framing, quote and evidence retrieval, supplier comparison and total-cost review, independent recommendation audit, and approval-ready publication. |
| Research Assistant | Ordered evidence, autonomous-research, verification, and publication pipeline. |
| Software Architecture Advisor | Ordered air-gapped advisory pipeline: source validation, static graph evidence, architecture review, implementation-prompt authoring, and audit/publication. |
| VC Assistant | Fan-out/fan-in: ordered evidence preparation leads to seven independent valuation-method scorers, then an all-success score-consistency join. Per-method state files prevent scorer artifact races, while the RAG skill brokers all Milvus Lite operations through one job-scoped connection. |

## Authoring rules

- Use `requires`/`provides` in `mn.workflow/v1` manifests to declare
  data dependencies. The converter produces the corresponding DAG edges.
- Use `trigger_rule` on a step for joins and failure-aware transitions. Core
  supports `all_success`, `all_done`, `one_success`, `one_done`, `one_failed`,
  `none_failed_min_one_success`, and `quorum_success` (with `quorum`).
- Set `agent_id` when a logical step is driven by a differently named runtime
  node, such as an ingress router or long-running service module.
- Keep a linear relationship only when later work mutates or depends on the
  same ordered state. Do not create parallel routes that race on shared
  artifacts.
- For service-owned dynamic work, such as Drug Discovery's per-target and
  per-candidate workers, retain the service as the runtime DAG step and let it
  gather immutable worker artifacts before reporting. Use Core dynamic scatter
  events when workers themselves must become addressable workflow steps.

Validate a source blueprint and inspect the executable DAG with:

```bash
mn-manifest-converter expand manifest.json --output build/manifest.executable.json
mn-manifest-converter check manifest.json --against build/manifest.executable.json
```
