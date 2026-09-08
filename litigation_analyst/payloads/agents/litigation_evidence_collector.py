from domain.round_tasks import collect_evidence
from ._binding import bind_child

run = bind_child(collect_evidence)
