# Research Assistant

This blueprint hard-requires at least one GPU with at least 49,152 MB of memory. MirrorNeuron validates this requirement before scheduling.

`Blueprint ID:` `research_assistant`  
`Category:` `Science`

Research Assistant turns a research goal and an approved evidence folder into a source-grounded research packet. After evidence collection, independent evidence-coverage and experiment-readiness assessments run in parallel. The hypothesis worker waits for both artifacts before synthesizing the packet. This is a workflow fork and join; hypothesis development still runs within one isolated specialist.

The autonomous specialist receives its configured LLM through the same SDK-backed blueprint support client used by VC Assistant. The blueprint requests the logical `default` model and the runtime selects the concrete model automatically. Normal runs require live model-backed analysis and fail instead of silently publishing a deterministic fallback; quick tests remain deterministic. Generated experiment code is proposal material only; this workflow does not yet have the exact batch-approval grant required to execute it.

Like VC Assistant, the blueprint declares `llm.model` as logical `default` and
does not declare a machine-specific model, endpoint, or placement. MirrorNeuron
owns model selection and routing; the payload only calls the configured actor
client supplied by the runtime.

Version 4.0.2 sends a phase-specific strict JSON Schema for every research phase
and specialist review, and declares the model's `structured_output` capability
as required. `payloads/domain/model_contracts.py` owns the field,
type, array, identity and source-reference contracts. The SDK constrains model
generation and validates the returned object against the same schema before
research normalization or publication. A contract mismatch gets one bounded
repair attempt; an unusable live response fails without synthetic replacement.
This requires the SDK's schema-aware `generate_json(response_schema=...)`
contract; older clients fail explicitly. Configuration-document `$schema` URLs
and `strict_json` alone do not define model response fields. Runtime admission
or HTTP failures remain request failures, rather than JSON syntax failures.

Version 1.3.0 requires one GPU with at least 49,152 MB of memory.
The runtime selects a compatible default model; the blueprint does not pin
Nemotron-specific parameter or quantization hints.
Required live analysis, the 16,384-token context request and review boundaries
are unchanged.
It also corrects the public research orchestrator minimum to the published
`1.3.49` release, whose runtime modules match the current source.

It is inspired by the role separation in Google's AI co-scientist—not a reproduction of Google's system. The workflow uses an explicit evidence ledger and bounded review roles so that generated hypotheses remain hypotheses until a qualified person evaluates them.

## Quick Start

```bash
mn blueprint run ./research_assistant
```

The default output folder is `~/Downloads/research-assistant`. Run-store artifacts are also written under `~/.mn/runs/<run_id>/`.

Like VC Assistant, every executable specialist runs through the runtime's
shared Docker-worker path. `frame_research_problem` and
`build_research_evidence` prepares deterministic context;
`assess_evidence_coverage` and `assess_experiment_readiness` run in parallel;
`develop_and_challenge_hypotheses` runs the isolated autonomous specialist; and
`verify_and_publish_research_packet` performs deterministic audit and report
publication. The autonomous phases stay inside one job-scoped worker invocation.
Generated code is not executed by this workflow.

## Process and agents

1. `research_goal_framer` normalizes the question, constraints, success criteria, and explicit unknowns.
2. `research_evidence_curator` creates the local/public evidence ledger and keeps run metadata separate from evidence.
3. `research_evidence_reviewer` records source coverage and gaps while `research_experiment_planner` records data availability and missing execution approvals. Each writes a separate branch artifact under the run's workflow state.
4. `autonomous_researcher` joins both assessments, then performs a bounded, multi-pass research procedure inside the isolated Docker worker: source-by-source analysis; question decomposition; competing-hypothesis generation; a separate adversarial review for each hypothesis; gap-directed tool/code planning; evidence-based revision; experiment design; independent meta-review and ranking; and a final executive synthesis.
5. `research_packet_auditor` verifies isolation trace, source refs, falsifiability, counterarguments, and review boundaries; `research_report_writer` then durably publishes the packet.

The bundled baseline CSV contains 12 synthetic robotics-simulation runs across
Isaac Sim, Gazebo, and MuJoCo so the sample can form measurable hypotheses
rather than generic prose ideas.

## Inputs

- `research_goal`: required outcome, mechanism, or problem to investigate.
- `research_domain`, `research_question`, and `scope`: optional framing and boundaries.
- `success_criteria` and `constraints`: evaluation rules, safety/ethics boundaries, and required review gates.
- `seed_hypotheses`: optional human-provided starting ideas that the workflow must challenge, not endorse automatically. A seed may be a statement string or a structured test contract with its prediction, counterargument, disconfirming observation, assumptions, relevant source refs, and experiment procedure.
- `input_folder`: local papers, notes, datasets, and evidence approved for the run. The bundled `examples/sample_inputs` folder is available in every workflow worker; provide an absolute path for your own material.
- `output_folder`: destination for the research packet and supporting ledgers.

The bundled sample evaluates shared robotics simulation infrastructure for
manipulation, navigation, and multi-robot teams. It is deliberately limited to
desk research and offline simulation planning; it does not modify live robots
or production simulators.

## Research Roles

The blueprint assigns bounded responsibilities across a topic finder, literature reviewer, idea generator, skeptic, proximity/novelty reviewer, experiment designer, code and benchmark planners, result analyst, paper writer, and meta-reviewer. Each role preserves evidence references or marks an assertion as an inference, hypothesis, or unknown.

Public research uses `web_browser_skill` standard mode, which starts with
lightweight w3m extraction and invokes its policy-governed rendered browser only
when needed. Queries are limited to sanitized research goals and questions. The
workflow does not send private documents, credentials, participant data, or raw
confidential notes to public search. Blocked pages, login walls, CAPTCHAs, stale
sources, and evidence conflicts are recorded rather than bypassed.

## Outputs

The output folder contains:

- `research_packet.json` — goal, evidence, ranked hypotheses, critiques, experiment concepts, and review boundary.
- `research_brief.md` — readable draft of the same packet.
- `evidence_ledger.json` — local and public source records, status, and retrieval time.
- `hypothesis_ledger.json` — candidate hypotheses, predictions, counterarguments, and ranking posture.
- `review_ledger.json` — human-review and blocked-action status.

After the draft packet is written, the run creates an OtterDesk human review request
for that exact packet digest. A reviewer can approve the draft for internal review,
request changes, or reject it. The request does not grant permission to execute an
experiment, publish findings, contact participants, or take another consequential
action. A revised packet gets a new request.
- `workflow_state/evidence_coverage.json` and `workflow_state/experiment_readiness.json` in the run store — parallel preflight results, also included in `research_packet.json`.
- `artifact_quality.json` and `run_health.json` — artifact and run checks.

Packets with at least one extracted local document or observed public source are `review_ready`. If neither is available, the full diagnostic bundle is still written, but the packet and quality report are marked `needs_evidence`; its next steps tell the customer whether to supply local material or retry retrieval. Run metadata is tracked separately from evidence references and never qualifies a packet as source-grounded.

The brief exposes the question decomposition, cross-source agreements and
tensions, the executed research procedure, per-hypothesis critiques and
rankings, and complete review-only test procedures with units, baselines,
outcomes, decision rules, analysis plans, and stop conditions. Generation
provenance records every model and fallback call plus the completed phase count.
Source links mean relevant context unless the source itself reports the
observation; they never validate a hypothesis.

The blueprint does not run unapproved experiments, make a validated scientific or clinical claim, publish or submit a manuscript, contact research participants, or make consequential safety decisions. A person must review and approve any such action.

This release does not yet implement persistent research epochs, G0/G1/G2 decision gates, or a numerical simulator. The two preflight branches make planning and evidence limits explicit, but they do not turn the current research packet into an approved experiment.

## Shared job data

The stable research job seeds bundled knowledge once and reuses its
`knowledge/`, `databases/rag/`, and `state/` resources across runs. Hypothesis
inputs, evidence, and reports remain run-scoped; another job gets an independent
store.

## Payload layout

`extensions/blocks.json` declares single-specialist phases. The remaining
`payloads/steps/verify_and_publish_research_packet.py` declares the audit/publish
sequence. Registry entries bind directly to the owning functions in
`payloads/domain/`. SDK blocks own worker setup, artifact integrity, model
budgets and publication; no blueprint runtime or compatibility adapter is used.

## Persistent conversation

OtterDesk can ask this hired co-worker about its research role, schedule,
latest hypotheses, or evidence gaps through the stable Job response service even
before its first run or while idle. Conversation never starts research or an
experiment.

Report publication preserves the complete saved brief in
`context_sources/outputs/<run-identity-hash>/`. The document skill owns conversion
and source receipts; the Job responder uses Membrane source intelligence for
cited report questions. Curated capability RAG remains separate. Missing or
oversized source evidence remains an explicit query failure.

## Validation

```bash
.venv/bin/python -m pytest -q
```

## Block composition (4.0.1)

All seven specialist handlers consume native block contexts and committed artifact references directly. Five single-specialist phases use declared domain-operation blocks; the final audit/publish sequence retains its StepSpec graph. Both preflight branches must reference the same captured evidence, and changed evidence fails before model work.

The research procedure records its evidence and authored-configuration identity and freezes completed analysis with an SDK checkpoint. Core may retry incomplete read-only analysis with the same evidence and authored configuration, including Core-authorized allowance increases; a stale start marker does not require manual reconciliation. Completed analysis replays without model calls, including recovery after an interruption while saving the final state. Strict live-model errors retain the provider failure instead of replacing it with fallback output.

Publication requires a completed packet audit and uses SDK artifact publication and document conversion. The two preflight branches, join, isolated research worker, live-model requirement and human experiment authority remain intact.

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.

## Context engine contract

The `mn.context` descriptor explicitly disables Membrane runtime recall for this blueprint: its payload does not call TextMemory. Existing domain knowledge/RAG, live status, MCP controls, and Core coordination retain their own contracts. The retired conversation-memory declaration is removed, so this workflow does not start a context compressor or require a Membrane SDK merely to launch. Any future runtime-memory consumer must declare `mirrorneuron-python-sdk[context]`, ingest complete preprocessed text under trusted job/run scope, and use the Markdown/DuckDB CPU service.

## Shared capability ownership

Runtime paths, structured LLM requests and knowledge retrieval use the SDK. Document extraction and bounded public-browser collection use the shared docs-to-markdown and public-research skills. Research questions, privacy rules, evidence policy, prompts and report composition remain blueprint-owned.

Version 1.2.1 uses the all-in-one `mirrorneuron-docs-to-markdown-skill` for document intake and OCR. Local source preparation stages the current skill; the retired document-reading and LLM OCR distributions are no longer required.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

## Conversation continuity and saved instructions

OtterDesk keeps the current topic, confirmed setup answers and pending question
with this hired co-worker. Short follow-ups refer to that dialogue; corrections
stay in the current conversation unless you explicitly ask me to remember them.
Ask one focused question when a short reply is ambiguous. During work, surface
useful findings, actual decisions and completion instead of routine step noise.

Chat > Memory lets you inspect, edit and forget explicit explanation preferences
and working rules. The next run captures the current list in
`inputs.payload.supervisor_instructions` and its content revision. Evidence revision, test-concept, synthesis and reviewer prompts receive it only
after public tool planning has ended; search planning and public queries do not. A changed or forgotten rule does not rewrite an active or historical run.
Preferences are not evidence and cannot authorize experiments, external actions
or weaker review gates.

For saved findings, use the selected run's prepared research brief through the
existing Membrane source intelligence. Keep source dates, evidence gaps and
historical status explicit. The app-owned
`payloads/prompts/conversation.json` supplies stage guidance to OtterDesk's native
conversation model; existing runtime memory and response contracts are unchanged.
