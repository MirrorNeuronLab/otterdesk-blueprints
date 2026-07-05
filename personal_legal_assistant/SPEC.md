# Personal Legal Assistant Spec

## Purpose

Provide one local review workflow for mixed personal or small-business legal document folders that contain invoices, bills, contracts, clause notes, labels, and supporting files.

## Capabilities

- Stage and classify local legal/payable documents.
- Extract invoice and utility bill fields for review.
- Extract contract clauses and source snippets.
- Compare clause coverage against a small playbook.
- Create an issue register across invoices and contracts.
- Write integrated review-only artifacts.

## Non-Goals

- Legal advice.
- Contract approval, redlining as final, signing, or counterparty contact.
- ERP posting, vendor creation, or payment submission.
- External sharing of confidential or privileged files without approval.

## Evaluation

A successful run writes the standard run store plus invoice, contract, issue-register, quality, health, and Markdown report artifacts. The final artifact must include evidence, next steps, source references, and blocked actions.
