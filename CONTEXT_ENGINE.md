# Catalog context engine contract

All 12 published entries in `index.json` declare the `mn.context` extension with
`text_memory.contract = mn.context.text.v1`. The profile is enabled only where
worker code actually ingests or retrieves runtime memory.

| Published blueprint | Markdown memory | Current boundary |
| --- | --- | --- |
| cctv_operator | Enabled | Camera/source-scoped sampled history before vision; job-scoped observations with run provenance |
| drug_discovery_research_assistant | Disabled | Discovery artifacts and knowledge; no TextMemory calls |
| software_architecture_advisor | Enabled | Complete frozen source text, runtime decisions and canonical memory recall |
| litigation_analyst | Enabled | Complete normalized case corpus, specialist observations and durable context turns |
| vc_assistant | Enabled | Complete redacted inputs, restricted input principals and normalized runtime claims, source qualification and method observations |
| financial_advisor | Disabled | Domain evidence/reporting and product knowledge; no TextMemory calls |
| research_assistant | Disabled | Investigation artifacts and product knowledge; no TextMemory calls |
| procurement_manager (`purchasing_manager`) | Disabled | Procurement evidence/decisions; no TextMemory calls |
| microduck_controller | Disabled | Simulation state and bounded MCP operations; no TextMemory calls |
| ros_amr_controller | Disabled | ROS state and bounded MCP operations; no TextMemory calls |
| gtm_planner | Disabled | Job MCP exchange and collaboration packets; no TextMemory calls |
| gtm_executor | Disabled | Job MCP exchange and collaboration packets; no TextMemory calls |

Unused conversation-memory declarations have been removed. Existing product RAG,
case databases, source-backed architecture graph tools and Core coordination are
separate facilities. Membrane's runtime memory requires no Redis.

```text
Complete upstream text / approved observations
                    |
              TextMemory v2
          trusted job + current run
                    |
       immutable Markdown revisions
                    |
         one derived DuckDB per job
                    |
      explicit passage / table / graph queries
                    |
          whole canonical spans / typed results
          + small external RAG response
          + witnesses in sidecar artifacts
                    |
          verified request admission
```

All entries declare SDK >=1.3.58.dev0,<2 in `dependencies.json` for these
profile/staging contracts. Active consumers additionally select the `context` extra. That extra requires Membrane SDK >=2.0,<3. Local development
stages the SDK and the matching Membrane source with `[grpc]` in one worker pip
transaction. Source/version validation fails before manifest mutation. Wheel and
Git preparation retain `[context]`; an installed optional package does not enable
an undeclared feature. All package versions advance for this descriptor change.

Set `text_memory.enabled=false` in a config override to disable the profile.
This overrides the descriptor and prevents context-service preparation. To add a
future consumer, declare the dependency, ingest complete preprocessed text through
`mn_sdk.text_memory.ingest_inputs`, and use explicit job/run scope. Conversion of
PDFs, spreadsheets and other original files stays upstream.

## Runtime prerequisites

Install the matching SDK, CLI, Membrane v2 image and current persistent Compose
template together. Source edits do not replace an installed v1 service. Source
installers can build the checked-out engine explicitly with
`mn-deploy/install.sh --mode local --build-membrane`; binary/GitHub installs need a
coordinated published release containing Membrane SDK 2 and its matching engine.
No old memory is migrated and no retired memory API is used by this catalog.

The trusted runtime supplies `MN_CONTEXT_ADDR`, `MN_CONTEXT_AUTH_TOKEN`, `MN_JOB_ID`
and `MN_WORKFLOW_RUN_ID`/`MN_RUN_ID`. The installer and CLI create/reuse a private
`context_auth.token`; workers receive the same credentials. Markdown and per-job
DuckDB files persist at the configured `MN_CONTEXT_FS_MEMORY_ROOT` volume. CPU
settings default to two DuckDB threads and 256 MiB; preparation never pulls or
starts a GPU compressor. Optional semantic embeddings require an offline local
CPU checkpoint. Lexical/graph retrieval remains available without embeddings.

`MN_CONTEXT_OBSERVABILITY=true` enables detailed authorized source/context/result
logging. Enable it in both the service and worker runtime. These logs contain
source and model content; witnesses remain outside model context.

Model calls managed by `ContextSession` additionally require a `VerifiedCounter`
validated against the selected serving provider, including tool/schema framing.
Byte limits and successful ingestion do not establish verified token admission.
Trusted runtime settings can bind the serving integration using
`MN_CONTEXT_TOKEN_COUNTER_FACTORY=package.module:create_counter`. The factory
receives `request`, `scope` and `principal` keyword arguments and returns a
calibrated Membrane `VerifiedCounter`; it must verify the actual selected route,
tools and schema framing. Install that module in the worker environment. Source
text and blueprint payload cannot select it. Without an integration, counting
remains unavailable for live managed Litigation/Architecture calls.
Unavailable counting blocks dispatch. This catalog audit does not certify those
live model flows or semantic answer quality.

## Verification

The catalog gates compile all 12 entries, resolve enabled/disabled overrides,
check imports and retired settings, and stage both source and binary dependencies:

```bash
python -m pytest tests/test_membrane_catalog.py tests/test_sdk_package_contracts.py -q
python -m pytest tests/software_architecture_advisor/test_runtime_memory.py -q
```

Architecture retains its frozen passage-retrieval packet if a graph provider fails and
retries, including the complete sideband receipt and replay binding. VC reporting
identifies Markdown/DuckDB runtime memory separately from Milvus product RAG.
Deployment gates use fake Docker/installer commands and temporary homes.
No context benchmark or GPU/model workflow was run for this audit.

The subsequent VC/CCTV context work preserves the distinction between external
knowledge and runtime observations: the knowledge provider retrieves a small
response, Membrane composes it with query-selected runtime evidence, and the
model boundary admits the complete request. Retrieved knowledge bodies are not
ingested as runtime memory. VC uses typed role/observation queries; CCTV queries
recent sampled camera history before each current-image call. Litigation and
architecture use bounded filesystem passages instead of whole recall bundles.

Membrane graph/table operations run in DuckDB. The source-backed structural
graph tools used by Litigation/Architecture remain a separate RGX skill; these
changes do not migrate their graph collectors or query language. Native Membrane
needle receipts prove its SQL execution and canonical source re-reads, while
injected answer recorders prove actual consumer composition only. Optional live
diagnostics measure pinned answering models separately. Neither source edits nor
component diagnostics certify a deployed full workflow.

Audit validation: 76 context/catalog packaging checks, the supplementary catalog
profile check, 221 SDK checks, 172 CLI checks and 40 deployment/dependency contract
checks passed. The two release-version checks changed by this audit also pass.
The broad catalog run initially had 57 failures; its post-change run had 53,
including two outdated version assertions subsequently repaired and rerun.
The remaining failures concern existing domain contracts, unpublished/obsolete
blueprint paths, stale RAG test adapters and local socket restrictions. They are
not passing context tests, and this audit does not certify full workflow success.
