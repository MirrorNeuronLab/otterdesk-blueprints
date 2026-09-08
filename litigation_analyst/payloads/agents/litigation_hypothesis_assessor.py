from domain.round_tasks import assess_hypothesis
from ._binding import bind_child

run = bind_child(assess_hypothesis)
