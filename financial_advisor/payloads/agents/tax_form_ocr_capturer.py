from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("tax_form_ocr_capturer", workflow.step_tax_form_ocr_capturer)

