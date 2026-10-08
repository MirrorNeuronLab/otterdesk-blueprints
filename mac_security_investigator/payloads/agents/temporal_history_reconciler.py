from domain.operations import reconcile
from ._binding import bind

run = bind(reconcile)
