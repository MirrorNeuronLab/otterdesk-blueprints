from purchase_domain.operations import retrieve_knowledge
from ._shared import create_domain_agent
run = create_domain_agent("retrieve_purchase_knowledge", retrieve_knowledge)

