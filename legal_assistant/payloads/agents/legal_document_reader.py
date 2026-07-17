from legal_domain.operations import read_documents
from ._shared import create_domain_agent
run = create_domain_agent("legal_document_reader", read_documents)

