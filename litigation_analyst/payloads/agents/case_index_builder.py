from domain.indexing import build_indexes
from ._binding import bind

run = bind(build_indexes)
