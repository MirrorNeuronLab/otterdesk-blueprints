from domain.verification import verify
from ._binding import bind

run = bind(verify)
