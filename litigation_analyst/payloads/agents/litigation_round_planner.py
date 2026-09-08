from domain.round_planning import plan_round
from ._binding import bind_child

run = bind_child(plan_round)
