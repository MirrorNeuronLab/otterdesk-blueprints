from domain.stages import generate_structures
from ._shared import create_domain_agent
run = create_domain_agent("structure_generation", generate_structures)
