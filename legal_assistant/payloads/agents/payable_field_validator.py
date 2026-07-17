from domain.invoices import validate_payables
from ._shared import create_domain_agent
run = create_domain_agent("payable_field_validator", validate_payables)

