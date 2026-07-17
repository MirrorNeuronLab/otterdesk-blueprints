from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("tax_form_ocr_capturer", legacy.step_tax_form_ocr_capturer)

