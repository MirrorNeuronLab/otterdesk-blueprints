from domain.evidence_tasks import query_graph
from ._binding import bind_child

run = bind_child(query_graph)
