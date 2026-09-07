# Litigation Analyst

A Docker-worker blueprint converted from `litigation_analyst_v2` on Spark.
It freezes legal sources, builds a persistent document index and observed graph,
then lets an LLM choose investigative enquiries using installed skill manuals.
A deterministic final stage validates citations and writes a review draft. All outputs remain drafts for human review.

## Prepare and run

Requires MirrorNeuron with the companion SDK, agents, and skills checkout,
Docker, Git, authenticated GitHub read access to `MirrorNeuronLab/mn-graph-engine`,
and an authenticated `gcloud` account with read access to
`mirrorneuron-public-packages/mn-graph-engine`. The new graph-analysis skill
must be installed from the companion checkout until its next package release:

```bash
export MN_WORKSPACE_ROOT=/path/to/mirror-neuron-set
export MN_SKILLS_ROOT="$MN_WORKSPACE_ROOT/mn-skills"
python -m pip install -e "$MN_SKILLS_ROOT/graph_analysis_skill"
cd litigation_analyst
python prepare.py
MN_USE_LOCAL_SKILLS=1 mn blueprint run ./
```

No input values are required. Preparation downloads the pinned synthetic
[EMC2 dataset](https://github.com/jur1st/emc-2) and the published, checksummed
MN Graph Engine 0.0.1 Linux binary. An omitted runtime `input_folder` downloads
EMC2 into that run's sample directory automatically. The configured local model
is selected and prepared by the SDK/DMR integration. Missing model service,
package, binary, or source inputs fail explicitly.

For your own documents, set the optional `input_folder` run input to an existing
local folder in OtterDesk. Optionally set `goal` and `output_folder`.
`python prepare.py --input-folder /path/to/case` prepares the engine without
fetching EMC2 and records the folder in `prepared/inputs.json`; pass that folder
in your launch inputs, for example:

```bash
MN_USE_LOCAL_SKILLS=1 mn blueprint run ./ --set inputs.payload.input_folder=/path/to/case
```

Platform local-input staging makes it visible in Docker.
A typo or empty custom folder never silently substitutes demonstration data.
Do not place generated output inside the input folder.

On Spark use ARM64 (`--target aarch64-unknown-linux-gnu`). For Linux x64 use
`--target x86_64-unknown-linux-gnu`. The engine is CPU-only and requires glibc
2.36 or newer, supplied by the Debian 12 worker image. Credentials are used
only by host preparation and are never copied into the image. The preparation
script builds the pinned platform Python wheel on the authenticated host; Docker
installs this generated wheel without GitHub credentials. The generated binary
and wheel directories are ignored by Git. The unchanged
platform Python dependency is pinned in `payloads/requirements.txt`; its current
package imports PyTorch even for document-only work. It supplies the original
content-addressed retrieval implementation, not trained litigation weights.

The graph skill is new source work. `MN_USE_LOCAL_SKILLS=1` uses the companion skill and agent
checkouts; a production non-development installation requires publishing their
graph skill version 1.3.23 first (existing dependencies retain their published versions). Preparation does not publish packages.

## Inputs and limits

The folder is recursively inventoried. UTF-8 text, CSV, Markdown, JSON, XML,
HTML, logs, `.eml`, and `.mbox` are read locally. Text PDFs use the shared PDF
extraction skill; supported office files use the shared AnyDoc converter.
Image-only PDFs, images, archives, unsupported encodings and conversion failures
are explicitly listed as unreadable. There is no OCR, archive unpacking, audio
transcription, legal classification, exhaustive search, or financial calculation.
Extract those sources to text before relying on coverage. Source documents are
never executed. Symlinks are rejected.

The default bounds are 5,000 files, 32 MiB per file, 256 MiB total source bytes,
24 skill invocations, 40 model decisions and 600 seconds of investigation time.
Graph queries require LIMIT <=50. Operator tunables are in `config/default.json`.
Retrieval uses the document skill's persistent SQLite FTS5 lexical index with
exact text spans. It replaces the previous transient hashing retrieval in this
workflow; ranked results are not exhaustive or semantic search.

The agent reads packaged SKILL.md manuals through `read_skill`, then selects
registered operations with `invoke_skill`. Direct deterministic callers use the
same Python implementations. No skill is installed at runtime. Installed wheel
and editable packages carry the same manuals and descriptors.

Hypotheses track cited support, counter-evidence, alternative explanations,
uncertain identity, inferred assessments and outstanding enquiries. Evidence
cannot grant tools or override instructions. Only the frozen case can be queried.
Creation/import are restricted to the deterministic ingestion stage.

The shared bounded loop stores each decision before dispatch and each completed
observation before another model call. Completed calls are reused on restart;
an interrupted in-flight read may repeat. Evidence/configuration/manual changes
reject checkpoint reuse. Cancellation (`case/cancel.request`) is checked between
actions; POSIX main-thread deadlines bound blocking calls. Terminal partial
reports state cancellation, exhausted budgets and unresolved enquiries explicitly.

## Inspect outputs

Outputs live in the platform run directory under the configured output folder
(default `~/Downloads/litigation_analyst`). `review_index.json` locates:

- `review_draft.md`: neutral hypotheses, findings, citations, limitations and coverage.
- `case/source_inventory.json`: original file hashes, normalized source identities,
  sizes, and unreadable sources.
- `case/sources.json`: frozen, exact text used by every character-span citation.
- `case/evidence.sqlite3`: sources, cited evidence, current hypotheses and reports.
- `case/agent_checkpoint.json`: model requests/responses, actions, results, errors, manual hashes and hypothesis revisions.
- `case/documents.sqlite3`: persistent read-only passage index.
- `case/indexes.json`: source and index integrity receipt.
- `case/originals/`: original file bytes, named by SHA-256.
- `case/evidence.rgx`: observed document/email graph, built and checked before agent execution.

Draft citations refer to normalized text hashes and exact character offsets.
Mailbox citations refer to decoded message headers/body text; original container
hashes remain in the inventory. Converted documents likewise retain original
file hashes and a separate extracted-text hash. Model assessments are inferred
review material; extracted email relationships do not establish identity,
knowledge, intent, liability, privilege, authenticity, or admissibility.

Review the database with a read-only SQLite connection. The response service is
for bounded role/setup questions, not confidential evidence or audit access.
No email, filing, publication, payment, or other external action is available.

## Validation

```bash
python -m pytest tests/test_manifest_contracts.py -q
python -m pytest tests/test_litigation_analyst.py tests/litigation_analyst -q
python -m pytest tests -q
git diff --check
```

Live model and Docker checks are opt-in; deterministic tests use synthetic
sources and scripted models, retaining exact-span and audit assertions.
