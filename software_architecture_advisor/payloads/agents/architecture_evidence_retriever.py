from domain.evidence_tasks import search_evidence
from ._binding import bind_child

run = bind_child(search_evidence)
