from domain.tax import step_tax_form_ocr_capturer
from ._shared import create_domain_agent

run = create_domain_agent("tax_form_ocr_capturer", step_tax_form_ocr_capturer)

