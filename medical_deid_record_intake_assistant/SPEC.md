        # Medical De-Identification Record Intake Assistant Specification

        ## Purpose

        Hospitals, clinics, health-tech vendors, clinical research teams, and medical BPOs need local OCR and de-identification of PHI-bearing records before downstream use.

        ## Public Dataset Input

        The blueprint is seeded with `RootCauseAnalytics Healthcare Library Sample` as its public sample input source.

        - URL: https://huggingface.co/datasets/RootCauseAnalytics/Healthcare-Library-Sample
        - Alternate URL: n/a
        - Provider: RootCauseAnalytics on Hugging Face
        - License note: CC BY-NC 4.0 according to the public dataset/forum descriptions; review source terms before production use.
        - Download note: Use the Hugging Face dataset files or clone with git-lfs/huggingface_hub when available.

        ## OCR Skill

        The workflow uses `mn-skills/llm_ocr_skill` via `extract_document_folder(...)` and the Docker Model Runner LightOnOCR configuration. Embedded text is preferred; scanned PDFs and document images are routed through OCR only when needed. Downstream evidence preserves `ocr_required`, `extraction_method`, warnings, page metadata, and model metadata.

        ## Fields

        - `patient_name`
- `date_of_birth`
- `medical_record_number`
- `doctor`
- `medications`
- `diagnoses`
- `test_tables`
- `visit_dates`
- `redaction_spans`

        ## Workflow

        - Stage Medical Inputs: Resolve the medical document folder and synthetic healthcare sample input notes.
- Extract Medical Text: Read embedded text and call shared llm_ocr_skill only for scanned or low-text clinical pages.
- Detect PHI Entities: Detect patient, clinician, contact, date, identifier, account, address, and organization entities.
- Redact & Validate Medical Packet: Apply reviewable redactions, preserve source evidence, and compare to labels where available.
- Write De-ID Review Packet: Write a de-identification packet with redaction map, residual-risk notes, and reviewer checklist.

        ## Output Contract

        The final artifact contains the standard OtterDesk fields:

        - `type`: `medical_deidentification_review_packet`
        - `executive_summary`
        - `recommended_action`: `privacy_officer_review_required_before_release`
        - `confidence`
        - `evidence`
        - `next_steps`
        - `source_refs`

        ## Safety Rules

        - All extracted values are review-only.
        - Human approval is required before downstream release or system sync.
        - Logs and events must redact regulated and confidential identifiers.
        - Dataset licenses and terms remain the operator's responsibility.
