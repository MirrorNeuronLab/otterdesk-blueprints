# Architecture review knowledge (MVP)

Twelve short, authored review cards. These are starting points for falsifiable investigations, not universal rules or an exhaustive architecture textbook. The sourced cards paraphrase public methods; the other cards are explicitly labeled original MVP heuristics. The checks and exceptions are our application of those ideas, not quotations or claims that the authors reviewed this software.

Edit `practices.json` to maintain the executable library. Every card needs a stable `K` ID, families, keywords, principle, verification check, exception, origin and source list. No library is loaded from an analyzed repository automatically.

Retrieval ranks exact investigation-family matches and goal keywords locally. Each model input receives at most two cards and 1,200 UTF-8 bytes by default; a tight context budget can reduce this further. The library causes no additional graph builds, embedding requests or LLM calls. Source links are for the reviewer and are never fetched during analysis.

Selected cards and the library version/hash are preserved in each run’s `knowledge.json`. Cards are guidance; only executed query and source IDs can support factual claims. Offline runs retrieve cards for the reviewer and Codex prompts but perform no LLM reasoning.

## K01: Quality scenarios and tradeoffs

Families: coupling, runtime, configuration.

Judge a design against a concrete quality goal and its competing costs.

**Check:** Define a workload or failure scenario, baseline and measurable response; compare a small change with keeping the design.

**Exception / counter-check:** Static degree cannot establish latency, business impact or a universal severity threshold.

Origin: original review checklist inspired by source.
Source: [SEI: ATAM](https://www.sei.cmu.edu/library/atam-method-for-architecture-evaluation/).

## K02: Cohesion and bounded contexts

Families: coupling, responsibility, team_ownership, duplication.

Group behavior that shares vocabulary, invariants and reasons to change.

**Check:** Compare call/state paths, domain terms and change reasons; test one local seam before choosing a deployment boundary.

**Exception / counter-check:** High degree or several collaborators may be cohesive orchestration; shared atomicity may justify staying together.

Origin: original review checklist inspired by source.
Source: [Martin Fowler: Bounded Context](https://martinfowler.com/bliki/BoundedContext.html).

## K03: Ports, adapters and dependency direction

Families: layering, abstraction.

Keep application policy testable through explicit boundaries to external technology.

**Check:** Obtain the allowed dependency rule, trace one violating edge and test the policy through a local port.

**Exception / counter-check:** A layer name is not a rule; an adapter may intentionally import infrastructure. Avoid interfaces without a useful seam.

Origin: original review checklist inspired by source.
Source: [Alistair Cockburn: Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/).

## K04: Retries and idempotent effects

Families: resilience, workflow.

Repeated attempts for the same logical operation need an explicit effect and response contract.

**Check:** Trace request identity and deduplication storage; inject timeouts before and after effects, then repeat the operation.

**Exception / counter-check:** A retry wrapper alone proves nothing; a local rollback cannot undo an external effect.

Origin: original review checklist inspired by source.
Source: [AWS Builders Library: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).

## K05: State ownership and atomicity

Families: ownership, data_flow, schema_evolution.

Assign authority for state changes around the invariants that must remain atomic.

**Check:** Resolve physical stores and actual writers; trace commit boundaries and characterize competing writes before extraction.

**Exception / counter-check:** A table name is not database identity; reads do not prove shared ownership. A local transaction may be the right boundary.

Origin: original MVP heuristic.

## K06: Characterization and architecture checks

Families: verification.

Protect observed behavior before changing a structural boundary.

**Check:** Trace a real call to its state or external effect; test a normal and failure path, then encode the agreed dependency rule.

**Exception / counter-check:** A test-file link is not coverage; doubles can hide integration failures. Test the contract, not private layout.

Origin: original MVP heuristic.

## K07: Architectural decisions and drift

Families: intent_verification, drift, configuration.

Keep the context and consequences of significant decisions discoverable.

**Check:** Compare a current accepted decision with cited behavior; record its owner, status, alternatives and a checkable constraint.

**Exception / counter-check:** A superseded decision or intentional exception may explain a mismatch; document the change before declaring a violation.

Origin: original review checklist inspired by source.
Source: [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

## K08: Compatible interface evolution

Families: schema_evolution, abstraction, runtime.

Separate adding a compatible interface, migrating consumers and retiring the old contract.

**Check:** Inventory consumers and versions; exercise old/new compatibility, stage one migration and define a rollback checkpoint.

**Exception / counter-check:** Temporary dual support costs maintenance; an atomic in-process change may be simpler when every consumer is controlled.

Origin: original review checklist inspired by source.
Source: [Danilo Sato: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html).

## K09: Change and incident triage

Families: history, incident_analysis, team_ownership.

Use change patterns to select investigations whose behavior can be checked.

**Check:** Inspect the commit window, exclude mechanical changes and join explicit incident links before assigning incident impact.

**Exception / counter-check:** Co-change is correlation; a shared feature or generated files can explain it. Commit authorship alone is not ownership.

Origin: original MVP heuristic.

## K10: Trust boundaries and sensitive flows

Families: data_flow.

Verify protections where untrusted input crosses into sensitive state or execution.

**Check:** Trace a concrete source-to-sink path, authorization and validation; reproduce a rejected unauthorized or malformed request.

**Exception / counter-check:** A lexical source/sink match is a candidate, not an exploit; framework validation or unreachable paths may disprove it.

Origin: original MVP heuristic.

## K11: Operational budgets and observability

Families: runtime, configuration, resilience.

Make dependency failure and resource limits observable against an explicit operational budget.

**Check:** Trace configured timeouts, queue or pool limits and propagation; measure one slow or failed dependency under a stated load.

**Exception / counter-check:** Declared topology is not a runtime trace; adding retries or queues may amplify load and change delivery semantics.

Origin: original MVP heuristic.

## K12: Workflow consistency and compensation

Families: workflow, ownership.

Define valid state transitions and recovery for multi-step effects.

**Check:** Map one workflow, durable progress and effect order; inject a crash between steps and test restart and duplicate delivery.

**Exception / counter-check:** Compensation is a new action, not time reversal; retaining one local transaction may be safer than splitting the workflow.

Origin: original MVP heuristic.
