from domain.tax import step_tax_llm_reviewer
from ._shared import create_domain_agent

run = create_domain_agent("tax_llm_reviewer", step_tax_llm_reviewer)

