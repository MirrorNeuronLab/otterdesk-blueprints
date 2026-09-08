from domain.round_tasks import summarize_round
from ._binding import bind_child

run = bind_child(summarize_round)
