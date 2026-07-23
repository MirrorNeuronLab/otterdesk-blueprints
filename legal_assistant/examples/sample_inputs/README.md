# Legal Assistant Sample Inputs

This folder contains synthetic invoice/bill and short-contract fixtures plus a real public federal contract-terms PDF for a substantive local review run.

It also contains a synthetic payment-instruction change notice. The notice is
deliberately unsupported by the invoice and contract packet; a credible review
must quarantine it for independent vendor verification rather than treating it
as authority to change payment details.

`far_52_212_4_contract_terms.pdf` is FAR 52.212-4, “Contract Terms and Conditions—Commercial Products and Commercial Services,” downloaded from the official [Acquisition.gov page](https://www.acquisition.gov/far/52.212-4) and its [printable PDF endpoint](https://www.acquisition.gov/node/31867/printable/pdf). It is included to exercise the OCR/embedded-text document-ingestion path and deep clause-risk review. The official page lists FAC 2026-01 and an effective date of March 13, 2026; verify the current source before using the workflow for a real matter.

The packet is review-only. The runner should use the OCR skill for PDFs/images when embedded text is insufficient, index the checked-in `knowledge/` playbook with the RAG skill, and pass retrieved citations into the live LLM prompts. The government clause is a demonstration input, not legal advice and not a substitute for a matter-specific attorney review.
