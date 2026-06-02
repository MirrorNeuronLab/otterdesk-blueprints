        # Tax Form OCR Capture Assistant Specification

        ## Purpose

        CPA firms, tax-prep software teams, payroll providers, banks, and agencies need local OCR for taxpayer identity and financial fields with fewer third-party data transfers.

        ## Public Dataset Input

        The blueprint is seeded with `NIST Special Database 2 and NIST Special Database 6` as its public sample input source.

        - URL: https://www.nist.gov/srd/nist-special-database-2
        - Alternate URL: https://www.nist.gov/srd/nist-special-database-6
        - Provider: National Institute of Standards and Technology
        - License note: NIST free reference data; review source terms before production use.
        - Download note: Download the Special Database 2 or 6 ZIP from NIST, then point document_sources.folder_path at an extracted submission folder.

        ## OCR Skill

        The workflow uses `mn-skills/llm_ocr_skill` via `extract_document_folder(...)` and the Docker Model Runner LightOnOCR configuration. Embedded text is preferred; scanned PDFs and document images are routed through OCR only when needed. Downstream evidence preserves `ocr_required`, `extraction_method`, warnings, page metadata, and model metadata.

        ## Fields

        - `form_type`
- `taxpayer_name`
- `taxpayer_id`
- `wages`
- `deductions`
- `credits`
- `line_items`
- `computed_totals`
- `field_locations`

        ## Workflow

        - Stage Tax Form Inputs: Resolve the tax-form folder and NIST sample input notes.
- Extract Tax Form Text: Call shared llm_ocr_skill for tax form images and scanned forms, preserving page and OCR metadata.
- Classify & Locate Fields: Classify form faces and locate taxpayer, wage, deduction, credit, and total fields.
- Validate Tax Capture: Compare captured values to answer files when available and flag arithmetic or OCR issues.
- Write Tax Capture Packet: Write a review-only structured tax capture packet and validation checklist.

        ## Output Contract

        The final artifact contains the standard OtterDesk fields:

        - `type`: `tax_form_ocr_capture_packet`
        - `executive_summary`
        - `recommended_action`: `review_captured_fields_against_source_forms_before_tax_use`
        - `confidence`
        - `evidence`
        - `next_steps`
        - `source_refs`

        ## Safety Rules

        - All extracted values are review-only.
        - Human approval is required before downstream release or system sync.
        - Logs and events must redact regulated and confidential identifiers.
        - Dataset licenses and terms remain the operator's responsibility.
