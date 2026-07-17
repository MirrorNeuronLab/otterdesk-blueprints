# Product Readiness Retrieval Notes

Use this guidance when preparing actor prompts or final review text.

The assistant is useful when a user has a folder containing mixed legal and payable documents: vendor agreements, service contracts, invoice PDFs, utility bills, structured labels, clause notes, or supporting correspondence. The workflow should intake local files, extract review evidence, write artifacts, and stop before any external action.

Review-ready output should include:

- a source-grounded invoice and bill extraction packet;
- a contract clause matrix with source snippets;
- a playbook comparison that flags missing or risky terms;
- an issue register with severity and review owner;
- a Markdown report suitable for attorney, human, or operations review;
- an action ledger that proves blocked actions remained blocked.

Quality checks should look for evidence coverage, missing critical payable fields, missing required contract clauses, OCR-required documents, and review-only boundary language. If inputs are too thin, the report should say that rather than inventing fields or clauses.

The highest-risk failures are treating the output as legal advice, approving payment from unverified fields, sending a contract for signature, sharing privileged documents externally, or contacting a counterparty/vendor without review. These actions must remain blocked.
