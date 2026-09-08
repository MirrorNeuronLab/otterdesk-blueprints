# Litigation Analyst specification

Version 2.0.0 changes the default investigation topology from one autonomous tool
loop to an LLM-planned, Core-managed child workflow. Input and final report paths
remain compatible. Existing runs retain their staged implementation; no old audit
is migrated or silently re-investigated.

## Product and ownership

The product accepts an optional legal-document folder and neutral goal. Omission
selects the pinned public EMC2 synthetic sample; invalid custom inputs fail.
Four fixed phases prepare sources, verify document/graph indexes, investigate,
and publish a draft. The investigation parent initializes context; its child
planner commits enquiries using only declared templates. Core alone admits and
executes the graph and releases the parent output after the final stop plan.

The LLM selects enquiries, evidence searches, optional admitted graph views, assessments
and acceptance decisions. Workers execute committed tasks deterministically;
replanning occurs between completed rounds. Up to two enquiries per round and
three rounds produce at most seven steps per round. Evidence, assessment and
independent review workers run serially to avoid competing SQLite mutations.
Unchanged repeated enquiry work stops with an explicit coverage limitation.
Model/validation/tool failures fail the workflow, not a simulated successful
investigation. Cancellation and elapsed deadlines are checked between rounds.

## Evidence and review contract

Ingestion freezes original bytes and normalized text with SHA-256 and exact span
provenance, reports unreadable formats, and rejects symlinks and empty custom
corpora. The graph skill owns graph execution and binary preparation; the document
skill owns persistent FTS5 lexical retrieval. No neural embedding feature is added.
Graph queries are read-only with literal LIMIT <=50 and case-scoped execution.

Every enquiry collects distinct support and counter searches. The assessor receives
complete, bounded passages and explicit omitted counts. SDK context admission
budgets the full schema and guidance before selecting whole evidence records;
omitted records cannot be cited by the assessment. The model's structured output
restricts citations to visible evidence IDs and preserves committed task IDs;
an empty evidence packet permits only an inconclusive assessment without findings.
No match is not evidence
of absence. Potential privilege flags exclude source passages from findings.
Assessments preserve uncertainty and ordinary explanations. Each finding cites
only visible verified evidence, at most 2,000 UTF-8 bytes, and a separate reviewer
must accept it before it enters narrative output. Final rendering revalidates
all retained source hashes and exact offsets. Graph results remain derived exhibits,
not allegations or independent corroboration. Attributed background guidance is
methodology, never evidence or an assumption of applicable jurisdiction.

## Artifacts and compatibility

Immutable proposals, task inputs, evidence, assessments, reviews, round summaries
and model receipts live in `case/rounds/`. A final checkpoint projection preserves
the existing citation-checking and rendering interfaces. Evidence SQLite, source
inventory, original bytes and normalized sources retain their existing contracts.
Authoritative reports remain on SDK-provided Syncthing shared run storage; Downloads
is an additional host export. Messages carry artifact references and bounded counts.
Core and shared agent lifecycle own replay and task completion; SDK working context
owns durable provider receipts. Raw evidence never enters the response service.

The previous autonomous explorer remains in `domain.app.agentic` and
`domain.research.investigate`, including its tests and historical documentation.
It is not an automatic fallback and has no default workflow binding.

## Acceptance and limits

Tests must compile admitted child templates with Docker workers; demonstrate an
LLM-directed second round informed by earlier observations; preserve stable
hypothesis identity; reject tampered task references, unsafe queries and invented
citations; withhold rejected findings; prove completed work replay does not invoke
models again; and retain the autonomous explorer's existing regression suite.
Live acceptance observes actual child tasks through report completion and matching
shared-file hashes on both nodes, using `default` → Nemotron on Spark.

Outputs are drafts for human review. Legal advice, source authentication, exhaustive
search, OCR, external acquisition/contact, legal filing and autonomous publication
are non-goals. Failed and incomplete investigations are never presented as verified
legal conclusions.

The graph planner selects named chronology, sender, recipient or document views.
Their RGQL is authored and validated by the blueprint; the LLM cannot submit arbitrary graph syntax.
