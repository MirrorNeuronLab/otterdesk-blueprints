from domain.round_tasks import review_finding
from ._binding import bind_child

run = bind_child(review_finding)
