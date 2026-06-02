        # Invoice Bill Extraction Assistant Specification

        ## Purpose

        AP, ERP, BPO, and utility billing teams need private extraction of supplier pricing, tax identifiers, customer data, bank details, and spending patterns from high-volume invoice and bill PDFs.

        ## Public Dataset Input

        The blueprint is seeded with `IDSEM Dataset` as its public sample input source.

        - URL: https://zenodo.org/records/6373179
        - Alternate URL: n/a
        - Provider: University of Las Palmas de Gran Canaria on Zenodo
        - License note: Dataset record on Zenodo; review source terms before production use.
        - Download note: Use the reduced preview first; the full idsem.zip is large.

        ## OCR Skill

        The workflow uses `mn-skills/llm_ocr_skill` via `extract_document_folder(...)` and the Docker Model Runner LightOnOCR configuration. Embedded text is preferred; scanned PDFs and document images are routed through OCR only when needed. Downstream evidence preserves `ocr_required`, `extraction_method`, warnings, page metadata, and model metadata.

        ## Fields

        - `supplier_name`
- `customer_name`
- `invoice_id`
- `tax_id`
- `due_date`
- `total_amount`
- `line_items`
- `consumption_fields`
- `billing_period`

        ## Workflow

        - Stage Invoice Inputs: Resolve the local invoice folder and public IDSEM sample input notes.
- Extract Invoice Text: Read embedded text and call shared llm_ocr_skill only for scanned or low-text invoice pages.
- Extract Payable Fields: Extract supplier, customer, tax, due-date, total, line-item, and consumption fields.
- Validate Invoice Packet: Compare extracted fields to labels when JSON references are available and flag approval blockers.
- Write Invoice Packet: Write a review-only payable extraction packet with source evidence and routing notes.

        ## Output Contract

        The final artifact contains the standard OtterDesk fields:

        - `type`: `invoice_bill_extraction_packet`
        - `executive_summary`
        - `recommended_action`: `review_extracted_invoice_fields_before_erp_or_payment_use`
        - `confidence`
        - `evidence`
        - `next_steps`
        - `source_refs`

        ## Safety Rules

        - All extracted values are review-only.
        - Human approval is required before downstream release or system sync.
        - Logs and events must redact regulated and confidential identifiers.
        - Dataset licenses and terms remain the operator's responsibility.
