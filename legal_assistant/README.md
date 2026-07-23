# Legal Assistant

`legal_assistant` merges invoice/bill extraction and contract clause review into one review-only local document workflow.

Put invoices, bills, contracts, clause notes, labels, or supporting files in the input folder. The blueprint extracts payable fields, maps contract clauses, compares playbook expectations, flags review issues, and writes a source-grounded packet to the output folder.

## Process and agents

The four logical steps separate runtime orchestration from legal work:

1. `prepare_legal_matter` inventories and reads sources with `legal_folder_watcher` and `legal_document_reader`.
2. `analyze_legal_documents` runs an invoice lane (`invoice_bill_extractor` → `payable_field_validator`) and a contract lane (`contract_clause_extractor` → `contract_playbook_comparator`) in parallel.
3. `reconcile_legal_review` merges both durable lane artifacts, builds the issue register, and audits the review with `legal_evidence_reconciler` and `legal_review_auditor`.
4. `publish_legal_review_packet` uses `legal_reporter` to write the final packet, priority queue, and obligation calendar.

Parallel lanes use separate state files, so contract and payable workers cannot
overwrite each other before the generated join completes.

## Inputs

- `document_folder` or `input_folder`: local folder containing legal and payable documents.
- `output_folder`: defaults to `~/Downloads/legal_assistant`.
- Optional `field_profile`, `matter_profile`, and `review_policy` values.

## Outputs

- Standard run-store files: `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, `final_artifact.json`.
- Domain artifacts: `invoice_bill_extraction.json`, `contract_clause_review.json`, `legal_issue_register.json`, `legal_assistant_report.md`, `action_ledger.json`, `artifact_quality.json`, and `run_health.json`.

## Substantive sample run

The bundled sample packet includes FAR 52.212-4, a real public federal contract-terms PDF. A normal run sends each specialist a bounded task prompt, uses the OCR skill for PDF/image ingestion when embedded text is insufficient, retrieves relevant sections of the checked-in legal playbook with Milvus Lite RAG, and calls the configured live LLM. The deep review artifact records clause-level findings, evidence gaps, risk flags, review questions, source refs, RAG citations, and confidence.

Model placement follows the cluster: the medium/Nemotron profile is preferred when MirrorNeuron advertises a usable `nemotron3` endpoint; otherwise the model catalog fallback selects the installed small/Gemma runtime. The effective choice is recorded in `llm_usage.runtime_selection`.

The sample review objective is contract-intake risk triage for a small-business operator and attorney. It asks the workflow to inspect payment controls, termination and continuity, indemnity and liability exposure, assignment/change-of-control effects, and privacy/privilege blockers without making a legal decision.

The sample also contains a synthetic payment-instruction change notice. The
expected control outcome is a high-priority quarantine-and-verify item: the
assistant must not treat new bank details as authenticated merely because they
appear in a document.

## Shared job data

Each configured legal-assistant job owns its knowledge, Milvus Lite database,
and durable state. Bundled playbook knowledge seeds only at initialization or
reset. Matter inputs and review packets remain run-scoped.

## Safety

Outputs are review-only. The assistant does not give legal advice, determine enforceability, approve contracts, sign documents, post invoices, submit payment instructions, contact vendors or counterparties, or share private/privileged data externally.

## Prompt contract

Specialist actors receive role-specific missions for intake, invoice/bill review, clause review, evidence reconciliation, audit, and report writing. The system prompt requires source hierarchy, explicit unknowns, deterministic-field invariance, bounded next steps, and a strict review-artifact JSON shape.

## Payload layout

`payloads/steps/` owns the four `StepSpec` graphs; `payloads/agents/` contains
nine same-named bindings. Focused modules under `payloads/domain/` own document
reading, invoices, contracts, evidence review, reporting, state, knowledge, and
runtime preparation. There is no workflow facade or generic operation router.
