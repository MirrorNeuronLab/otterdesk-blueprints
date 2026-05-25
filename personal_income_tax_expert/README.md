# Personal Income Tax Expert

Personal Income Tax Expert is a document automation co-worker for preparing a
reviewable federal Form 1040 draft packet from a local folder of tax documents.
It is designed for W-2, 1099-INT, 1099-R and 401(k) distribution forms, plus
related PDFs such as 1099-DIV, 1099-B, 1098, 1095-A, and brokerage statements.

The co-worker keeps the workflow private by default: it scans a local folder,
extracts embedded PDF text when available, marks scanned PDFs for LLM/OCR
review, maps evidence to likely Form 1040 lines, then runs a proposal and review
stage before writing the final packet.

## What It Produces

- A draft Form 1040 line map.
- A plain-English "What Is a 1040 Tax Form" explanation.
- Source evidence by document type and filename.
- Review warnings, assumptions, and missing-item questions.
- A personal tax advisor style message for OtterDesk chat.

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
written. The default is `~/Downloads`. The worker writes both
`*-final-artifact.json` and `*-report.md` when the selected folder is writable.

## Multi-Agent Flow

1. `document_intake_agent` scans documents, classifies forms, and flags OCR gaps.
2. `tax_proposal_agent` proposes conservative Form 1040 line mapping.
3. `tax_review_agent` checks assumptions, missing evidence, and filing risk.
4. `form_1040_packet_writer` writes the draft packet and advisor conversation.

## Advisor Voice

The co-worker should sound like a careful personal tax advisor: direct, warm,
source-grounded, and specific about what the user needs to confirm next.
It should not claim a return is filing-ready.
