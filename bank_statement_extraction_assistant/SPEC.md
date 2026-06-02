        # Bank Statement Extraction Assistant Specification

        ## Purpose

        Lenders, fintechs, SMB accounting tools, underwriting teams, and auditors need private extraction of account numbers, balances, merchant history, salaries, and cash-flow data.

        ## Public Dataset Input

        The blueprint is seeded with `AgamiAI Indian Bank Statement Synthetic Dataset` as its public sample input source.

        - URL: https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements
        - Alternate URL: n/a
        - Provider: AgamiAI on Hugging Face
        - License note: Apache 2.0
        - Download note: Use huggingface_hub or git-lfs to fetch a small sample before the full dataset.

        ## OCR Skill

        The workflow uses `mn-skills/llm_ocr_skill` via `extract_document_folder(...)` and the Docker Model Runner LightOnOCR configuration. Embedded text is preferred; scanned PDFs and document images are routed through OCR only when needed. Downstream evidence preserves `ocr_required`, `extraction_method`, warnings, page metadata, and model metadata.

        ## Fields

        - `account_holder`
- `account_number`
- `ifsc_or_routing`
- `statement_period`
- `opening_balance`
- `closing_balance`
- `transactions`
- `debits`
- `credits`
- `fees`

        ## Workflow

        - Stage Bank Inputs: Resolve the bank-statement folder and AgamiAI sample input notes.
- Extract Bank Text: Read embedded text and call shared llm_ocr_skill only for scanned or low-text statement pages.
- Extract Transaction Ledger: Extract account metadata, balances, transaction rows, debits, credits, fees, and running balances.
- Validate Statement Consistency: Reconcile opening, closing, and running balances and compare to JSON labels when available.
- Write Bank Statement Packet: Write a review-only bank statement extraction packet with cash-flow and exception notes.

        ## Output Contract

        The final artifact contains the standard OtterDesk fields:

        - `type`: `bank_statement_extraction_packet`
        - `executive_summary`
        - `recommended_action`: `review_transactions_and_balance_reconciliation_before_downstream_use`
        - `confidence`
        - `evidence`
        - `next_steps`
        - `source_refs`

        ## Safety Rules

        - All extracted values are review-only.
        - Human approval is required before downstream release or system sync.
        - Logs and events must redact regulated and confidential identifiers.
        - Dataset licenses and terms remain the operator's responsibility.
