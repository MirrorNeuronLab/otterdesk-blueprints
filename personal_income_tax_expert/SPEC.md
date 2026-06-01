# Personal Income Tax Expert Specification

## Purpose

Create a local-first tax document workflow that prepares a reviewable draft
federal Form 1040 packet from user-supplied tax PDFs. The workflow runs a
specialist LLM tax-preparation team and produces a draft review packet, not a
filing-ready return.

## Inputs

Primary input:

- `tax_documents.folder_path`: local folder containing source tax PDFs, TXT, or
  JSON test records.

Optional input:

- `tax_profile.tax_year`
- `tax_profile.filing_status`
- `outputs.folder_path`: output folder for prepared packet files; defaults to
  `~/Downloads`.
- `inputs.payload.document_folder`
- `inputs.payload.tax_year`
- `inputs.payload.filing_status`

## Form Knowledge

The blueprint uses local knowledge files and current IRS source anchors for:

- Form 1040 and Form 1040-SR.
- Publication 17.
- Form 1099-INT.
- Form 1099-R and 401(k) distribution review.
- 2025 standard deduction defaults for a basic draft packet.

## Extraction Rules

1. Read embedded PDF text where available.
2. Use the shared `llm_ocr_skill` for scanned PDFs and document images when
   Docker Model Runner is available; otherwise keep `ocr_required` warnings.
3. Redact SSNs, account numbers, and other tax identifiers in logs and run
   artifacts.
4. Classify known documents before mapping values.
5. Keep every mapped value tied to source document evidence.
6. Use LLM specialist agents to understand document meaning, extract fields,
   prepare workpapers, audit assumptions, and write the report, with
   deterministic fallback values for tests and offline runs.

## Agents

- Client intake coordinator: confirms scope and missing taxpayer facts.
- Document understanding agent: classifies documents and explains each form's
  tax role.
- Source field extractor: extracts box-level facts and source evidence.
- Income preparer: prepares income-line workpapers.
- Deductions and credits preparer: prepares deduction and credit review notes.
- Form 1040 assembler: maps supported facts to draft Form 1040 lines.
- Tax auditor: checks assumptions, unsupported credits/deductions, OCR gaps,
  schedule triggers, and missing documents.
- Manager reviewer: records blockers and keeps the packet not approved for
  filing.
- Advisor report writer: explains the result in plain English.
- Packet writer agent: writes `final_artifact.json` with the draft line map,
  advisor message, next actions, Markdown report, and PDF review packet.

## Output Contract

The final artifact contains:

- `type`: `prepared_1040_tax_packet`
- `title`: `Prepared Form 1040 Draft - What Is a 1040 Tax Form`
- `prepared_form_1040.line_map`
- `prepared_form_1040.source_evidence`
- `document_dossier`
- `preparer_workpapers`
- `audit_review`
- `manager_review`
- `llm`
- `advisor_message`
- `conversation_context`
- `review`
- `next_steps`
- `output_files` when packet files were written to `outputs.folder_path`

The status must remain `draft_needs_review` unless a future human-reviewed
filing workflow explicitly changes it.

When `outputs.folder_path` is writable, the worker writes a JSON packet,
Markdown report, and PDF tax review packet named with the blueprint id and run
id.

For `mn run`, the host-side `scripts/post-launch.sh` hook reads the completed
job event and materializes `result.json`, `final_artifact.json`, Markdown, and
PDF files outside the sandbox so CLI and OtterDesk users have durable outputs.

## Safety Rules

- Do not claim to be a CPA, attorney, or enrolled agent.
- Do not tell the user to file solely from this packet.
- Ask clarifying questions for filing status, dependents, address, itemized
  deductions, retirement distribution codes, self-employment income, and credits.
- Treat tax documents as regulated/confidential.
- Keep state tax returns out of scope unless a separate state workflow is added.
