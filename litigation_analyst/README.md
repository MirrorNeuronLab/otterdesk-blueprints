# Litigation Analyst

Litigation Analyst freezes a legal-document folder, validates its lexical document
index and observed graph, then investigates through **LLM-planned dynamic child
workflows**. Findings receive a separate evidence-grounding review before the
existing deterministic citation checks and report writer run. Outputs are drafts
for human review.

## Run on mini and Spark

Use the normal mini runtime connected to Spark; see the root AGENTS.md for the
operator-requested reinstall and node reconnection procedure.

```bash
mn blueprint run ./litigation_analyst --node mirror_neuron@10.0.4.26
mn blueprint run ./litigation_analyst --node mirror_neuron@10.0.4.26 \
  --set inputs.payload.input_folder=/absolute/path/on/mini/to/case
```

Omitting the folder downloads the pinned public EMC2 synthetic sample. Invalid
custom folders fail explicitly. The platform stages local inputs to the worker;
never replace the local path with a guessed Spark path. Inputs are frozen before
analysis, never executed or modified. Do not put outputs inside the input folder.

Models use the existing `default` LiteLLM route, which selects Nemotron on Spark
in this deployment. No Gemma override or autonomous-explorer fallback is added.
The graph-analysis skill prepares its published Linux engine and provider packages.
Local development requires the companion SDK, agents and skills repositories,
Docker, and authenticated package access as documented by that skill. Use
`MN_USE_LOCAL_SKILLS=1` with source installations. Preparation does not publish packages.

## Investigation rounds

The four parent phases remain source preparation → index building → investigation
→ reviewed draft publication. Investigation initializes a Core-managed child workflow:

1. The LLM planner chooses up to two falsifiable enquiries, distinct support and
   counter-evidence searches, and zero to two admitted read-only graph views per enquiry.
2. Core commits the round. An evidence collector executes each enquiry's bounded
   searches and graph queries, preserving exact source spans and audit records.
3. An assessor proposes a structured hypothesis and at most one cited finding.
4. A separate reviewer checks complete cited passages and accepts or withholds
   the proposed finding. A deterministic summary feeds the next planner decision.
5. The planner revises enquiries or stops. Replanning occurs only after all
   committed tasks complete; the parent cannot publish while children are running.

Tasks execute serially to protect the case evidence database. Core owns admission,
routing, retries, and completion; the blueprint only proposes admitted task templates.
The default is at most three rounds, two enquiries per round, and seven child steps
per round. `dynamic_investigation.max_rounds` can reduce the three-round ceiling;
`hypotheses_per_round` can be one or two. These bounds permit at most 24 retrieval/
graph operations and 16 model decisions, including the final stop decision.
Model responses are capped at 2,048 tokens. The existing elapsed deadline applies;
cancellation and deadline checks occur at planning boundaries. Failed specialists
fail the workflow explicitly rather than producing a successful-looking draft.

The previous fully autonomous exploration implementation and its tests remain
available for future stronger models. It is not wired into the default DAG.
See [Preserved autonomous explorer](AUTONOMOUS_EXPLORER.md) for that implementation's
entrypoint, context protocol, limits, and historical usage.

## Evidence and coverage

The document skill uses persistent SQLite FTS5 **lexical** retrieval, not semantic
embeddings. Ranked matches are not exhaustive, and no match never proves absence.
The observed graph is built and integrity-checked before investigation; graph
associations and centrality do not establish identity, intent or wrongdoing.
Each finding is limited to 2,000 UTF-8 bytes of complete cited evidence for review.
Oversized and additional passages remain in the evidence ledger and are explicitly
counted as omitted from the assessor's packet. No passage is silently shortened
and treated as complete evidence. Unsupported findings are withheld.

UTF-8 text-like formats, CSV, EML, mbox, extractable PDFs and supported office
formats are normalized locally. Unreadable files remain in coverage. No OCR,
archive execution, audio transcription, external acquisition or legal action is
available. Defaults allow 5,000 files, 32 MiB per file and 256 MiB total bytes.
Potential privilege flags exclude affected passages from substantive findings;
automatic screening does not replace a human handling decision. Background
methodology is attributed, separate from case evidence, and never assumed to be
applicable law. Source authenticity remains unverified.

## Inspect reports and audit

Authoritative files remain in the SDK-provided Syncthing shared run directory:

```text
$MN_HOME/shared/submissions/<submission-id>/outputs/runs/<run-id>/
```

`output_folder` (default `~/Downloads/litigation_analyst`) receives an additional
host copy. `review_index.json` identifies `final_report.md`, `evidence_appendix.md`,
`graph_appendix.md`, source/index receipts and the evidence database.

`case/rounds/` preserves immutable planner proposals, committed task parameters,
evidence observations, assessments, independent reviews, summaries and model
receipts. `case/agent_checkpoint.json` is the final review projection, retaining
the existing reporting contract; its mode is `dynamic_subworkflow`.
`case/context-memory/` contains SDK working-context receipts for live specialist
calls. Original bytes and normalized hashes/offsets remain under `case/`.
Only bounded coordination data and artifact references cross worker messages.
These artifacts are confidential; the response service does not expose them.

## Validation

```bash
python -m pytest tests/test_manifest_contracts.py -q
python -m pytest tests/test_litigation_analyst.py tests/litigation_analyst -q
python -m pytest tests -q
git diff --check
```

Deterministic tests exercise changed second-round plans, specialist ordering,
replay, cancellation, citation checks and preserved autonomous behavior. Live
runs additionally verify child completion and report replication between nodes.

The graph planner selects named chronology, sender, recipient or document views.
Their RGQL is authored and validated by the blueprint; the LLM cannot submit arbitrary graph syntax.
