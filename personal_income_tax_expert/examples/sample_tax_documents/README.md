# Sample Tax Documents

The blueprint ships sample text records in `config/default.json` so tests do
not need personal data or downloaded PDFs.

For real evaluation, use official IRS sample/current forms from:

- https://www.irs.gov/Form1040
- https://www.irs.gov/forms-pubs/about-form-1099-int
- https://www.irs.gov/forms-pubs/about-form-1099-r

Place downloaded or user-provided PDFs in a local folder and set
`tax_documents.folder_path` to that folder.
