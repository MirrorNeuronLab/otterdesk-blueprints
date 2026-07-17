from legal_domain.operations import compare_contracts
from ._shared import create_domain_agent
run = create_domain_agent("contract_playbook_comparator", compare_contracts)

