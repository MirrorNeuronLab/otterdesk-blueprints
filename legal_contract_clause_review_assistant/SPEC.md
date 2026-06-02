        # Legal Contract Clause Review Assistant Specification

        ## Purpose

        Law firms, in-house legal teams, CLM vendors, and diligence teams need private extraction of privileged or deal-sensitive contract terms without uploading client agreements to external services.

        ## Public Dataset Input

        The blueprint is seeded with `Contract Understanding Atticus Dataset (CUAD) v1` as its public sample input source.

        - URL: https://zenodo.org/records/4595826
        - Alternate URL: https://huggingface.co/datasets/theatticusproject/cuad
        - Provider: The Atticus Project on Zenodo and Hugging Face
        - License note: CC BY 4.0
        - Download note: Download CUAD_v1.zip from Zenodo or use the Hugging Face dataset for text-oriented experiments.

        ## OCR Skill

        The workflow uses `mn-skills/llm_ocr_skill` via `extract_document_folder(...)` and the Docker Model Runner LightOnOCR configuration. Embedded text is preferred; scanned PDFs and document images are routed through OCR only when needed. Downstream evidence preserves `ocr_required`, `extraction_method`, warnings, page metadata, and model metadata.

        ## Fields

        - `governing_law`
- `change_of_control`
- `assignment`
- `indemnity`
- `termination`
- `audit_rights`
- `renewal`
- `exclusivity`
- `liability`

        ## Workflow

        - Stage Contract Inputs: Resolve the contract folder and CUAD sample input notes.
- Extract Contract Text: Read embedded text and call shared llm_ocr_skill only for scanned or low-text contract pages.
- Extract Clause Matrix: Extract governing law, assignment, indemnity, termination, renewal, exclusivity, and liability evidence.
- Compare Contract Playbook: Compare extracted clauses against the supplied playbook and flag gaps or negotiation risks.
- Write Clause Review Packet: Write a review-only contract clause packet with source excerpts and attorney review questions.

        ## Output Contract

        The final artifact contains the standard OtterDesk fields:

        - `type`: `contract_clause_review_packet`
        - `executive_summary`
        - `recommended_action`: `attorney_review_required_before_relying_on_clause_findings`
        - `confidence`
        - `evidence`
        - `next_steps`
        - `source_refs`

        ## Safety Rules

        - All extracted values are review-only.
        - Human approval is required before downstream release or system sync.
        - Logs and events must redact regulated and confidential identifiers.
        - Dataset licenses and terms remain the operator's responsibility.
