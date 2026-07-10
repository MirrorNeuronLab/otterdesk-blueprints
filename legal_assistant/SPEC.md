# Legal Assistant Spec

## Purpose

Provide one local review workflow for mixed personal or small-business legal document folders that contain invoices, bills, contracts, clause notes, labels, and supporting files. The workflow is review-only and uses the standard blueprint contract for source-grounded actor prompts, explicit evidence gaps, and human approval boundaries.

## Prompt and Evidence Standard

- Deterministic extraction remains authoritative for fields, totals, classifications, counts, and source status.
- Specialist prompts separate observations, playbook comparisons, assumptions, and human-review questions.
- Every material finding keeps a source reference and uses explicit `unknown`, `not found`, `ambiguous`, or `review required` states when evidence is incomplete.
- The bundled playbook is a taxonomy and review checklist, not governing law or a substitute for qualified counsel.
- The final report preserves invoice/bill and contract domains separately, carries forward conflicts, and records bounded next steps with an owner and evidence request.

## Capabilities

- Stage and classify local legal/payable documents.
- Extract invoice and utility bill fields for review.
- Extract contract clauses and source snippets.
- Compare clause coverage against a small playbook.
- Create an issue register across invoices and contracts.
- Write integrated review-only artifacts and a strict JSON actor-review packet.

## Real Sample And Runtime Skills

The checked-in sample packet includes the official Acquisition.gov FAR 52.212-4 contract-terms PDF. The document reader uses `mirrorneuron-llm-ocr-skill` for PDF/image extraction when embedded text is insufficient, and the actor prompts use `mirrorneuron-rag-skill` to retrieve cited sections from the local legal playbook. Normal runs use the shared live LLM; fake/quick-test mode remains available for deterministic smoke tests.

## Non-Goals

- Legal advice.
- Contract approval, redlining as final, signing, or counterparty contact.
- ERP posting, vendor creation, or payment submission.
- External sharing of confidential or privileged files without approval.

## Evaluation

A successful run writes the standard run store plus invoice, contract, issue-register, quality, health, and Markdown report artifacts. The final artifact must include evidence, next steps, source references, the bundled playbook hash, specialist findings, and blocked actions.
