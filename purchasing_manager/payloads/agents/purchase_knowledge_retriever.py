from domain.intake import retrieve_knowledge

from ._shared import create_domain_agent


run = create_domain_agent("purchase_knowledge_retriever", retrieve_knowledge)
