# Personal Income Tax Expert

Personal Income Tax Expert is a document automation co-worker for preparing a
reviewable federal Form 1040 draft packet from a local folder of tax documents.
It is designed for W-2, 1099-INT, 1099-R and 401(k) distribution forms, plus
related PDFs such as 1099-DIV, 1099-B, 1098, 1095-A, and brokerage statements.

The co-worker keeps the workflow local-first by default: it scans a local
folder, extracts embedded PDF text when available, marks scanned PDFs for
LLM/OCR review, then runs a specialist tax preparation team over the evidence.
The default LLM endpoint matches the video blueprint: Ollama at
`http://192.168.4.173:11434` with `nemotron3:33b`.

## What It Produces

- A draft Form 1040 line map.
- Specialist preparer workpapers for document understanding, source extraction,
  income, deductions, credits, assembly, audit, and manager review.
- A plain-English "What Is a 1040 Tax Form" explanation.
- Source evidence by document type and filename.
- Review warnings, assumptions, and missing-item questions.
- A personal tax advisor style message for OtterDesk chat.
- Local JSON, Markdown, and PDF review-packet files when `outputs.folder_path`
  is writable.

The output is not a filed tax return. It is a draft packet for review by the
taxpayer or a qualified tax professional.

## Input Folder

Point `tax_documents.folder_path` to a local folder containing PDF forms. Common
examples:

- W-2 Wage and Tax Statement.
- 1099-INT Interest Income.
- 1099-R retirement, IRA, pension, annuity, or 401(k) distribution.
- 1099-DIV, 1099-B, 1099-NEC, 1098, 1095-A, and brokerage statements.

If no folder is selected, the blueprint uses bundled sample text records so the
conversation and output shape can be tested without personal documents.

## Output Folder

Set `outputs.folder_path` to choose where the prepared packet files should be
written. The default is `~/Downloads`. The worker writes
`*-final-artifact.json`, `*-report.md`, and `*-tax-review-packet.pdf` when the
selected folder is writable. If PDF rendering support is unavailable, the JSON
and Markdown files are still written and the final artifact records a warning.

## Multi-Agent Flow

1. `client_intake_coordinator` confirms scope and missing taxpayer facts.
2. `document_understanding_agent` classifies forms and explains their tax role.
3. `source_field_extractor` extracts box-level facts and source evidence.
4. `income_preparer` prepares income-line workpapers.
5. `deductions_credits_preparer` prepares deduction and credit review notes.
6. `form_1040_assembler` maps supported facts to draft Form 1040 lines.
7. `tax_auditor` checks evidence, OCR gaps, and unsupported schedules.
8. `manager_reviewer` holds the packet as not approved for filing.
9. `advisor_report_writer` writes the user-facing summary and next steps.
10. `form_1040_packet_writer` writes JSON, Markdown, and PDF artifacts.

## Advisor Voice

The co-worker should sound like a careful personal tax advisor: direct, warm,
source-grounded, and specific about what the user needs to confirm next.
It should not claim a return is filing-ready.
