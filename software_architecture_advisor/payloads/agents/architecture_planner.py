from domain.catalog_planning import planner
from ._binding import bind_child

run = bind_child(planner)
