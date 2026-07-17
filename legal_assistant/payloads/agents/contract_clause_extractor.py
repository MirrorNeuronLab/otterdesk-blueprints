from legal_domain.operations import extract_contracts
from ._shared import create_domain_agent
run = create_domain_agent("contract_clause_extractor", extract_contracts)

