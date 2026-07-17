"""First Chicago worker registered as ``first_chicago_scorer``.

The deterministic formula is implemented in ``domain.valuation.first_chicago``;
this module makes the executable agent binding directly discoverable.
"""

from .valuation_scorer import create_valuation_scorer


run = create_valuation_scorer()
