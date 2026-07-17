from domain.invoices import extract_invoices
from ._shared import create_domain_agent
run = create_domain_agent("invoice_bill_extractor", extract_invoices)

