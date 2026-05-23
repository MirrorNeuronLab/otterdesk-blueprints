# Personal Income Tax Expert Specification

## Purpose

Create a local-first tax document workflow that prepares a reviewable draft
federal Form 1040 packet from user-supplied tax PDFs.

## Inputs

Primary input:

- `tax_documents.folder_path`: local folder containing source tax PDFs, TXT, or
  JSON test records.

Optional input:

- `tax_profile.tax_year`
- `tax_profile.filing_status`
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
2. Mark blank/scanned PDFs as `ocr_required`.
3. Redact SSNs, account numbers, and other tax identifiers in logs and run
   artifacts.
4. Classify known documents before mapping values.
5. Keep every mapped value tied to source document evidence.

## Agents

- Document intake agent: classifies documents and checks OCR needs.
- Tax proposal agent: maps extracted values to likely Form 1040 lines.
- Tax review agent: checks assumptions, unsupported credits/deductions, and
  missing documents.
- Packet writer agent: writes `final_artifact.json` with the draft line map,
  advisor message, and next actions.

## Output Contract

The final artifact contains:

- `type`: `prepared_1040_tax_packet`
- `title`: `Prepared Form 1040 Draft - What Is a 1040 Tax Form`
- `prepared_form_1040.line_map`
- `prepared_form_1040.source_evidence`
- `advisor_message`
- `conversation_context`
- `review`
- `next_steps`

The status must remain `draft_needs_review` unless a future human-reviewed
filing workflow explicitly changes it.

## Safety Rules

- Do not claim to be a CPA, attorney, or enrolled agent.
- Do not tell the user to file solely from this packet.
- Ask clarifying questions for filing status, dependents, address, itemized
  deductions, retirement distribution codes, self-employment income, and credits.
- Treat tax documents as regulated/confidential.
- Keep state tax returns out of scope unless a separate state workflow is added.
