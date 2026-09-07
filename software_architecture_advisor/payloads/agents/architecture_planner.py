from domain.adaptive_planning import plan_architecture
from ._binding import bind_child

run = bind_child(plan_architecture)
