from domain.structural_analysis import analyze_snapshot
from ._binding import bind

run = bind(analyze_snapshot)
