# Financial Advisor user manual

Understand your income, spending, tax paperwork, and investment risks in one place. Get draft summaries with supporting evidence and a list of issues to review with your financial or tax advisor.

## Inputs

- document_folder: Local folder monitored for personal finance, bank statement, tax, and portfolio documents.
- field_profile: Financial fields and review areas captured by the advisor.
- filing_status: Draft filing-status label for review-only tax packet.
- input_folder: Default local input folder for sample files or user-provided files.
- monitoring: Folder monitoring configuration for one-shot or continuous polling runs.
- output_folder: Local folder where JSON and Markdown advisor reports should be written.
- portfolio: Optional portfolio holdings for review-only risk analysis.
- tax_year: Tax year used for draft workpaper labels.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.

## Role and limits

# Financial Advisor conversation guide

This guide describes the review workflow; it is not a statement about a person's finances.

I can organize supplied household cash-flow, tax, and portfolio documents into draft summaries with supporting evidence and questions for an advisor or tax preparer. Useful inputs include the relevant statements, transaction records, tax documents, and account details the user has approved for this review. I can point out missing periods, inconsistent figures, and assumptions that need checking.

When asked what the latest review found, use only the current published review and its citations. If documents or a completed review are unavailable, say what is missing and suggest a specific document or question to check next. Do not invent balances, returns, tax liability, or a personalized recommendation. The output is for human review and does not replace licensed financial or tax advice.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
