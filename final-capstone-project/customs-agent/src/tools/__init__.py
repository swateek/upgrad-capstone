"""Calculator tools. Each takes a pydantic Args model and raises ToolError on failure.

The model never does arithmetic (CLAUDE.md rule 1): every amount the writer may state
comes from one of these tools. Rules and rates are read from data/ (rule 3).
"""

from src.tools.check_restrictions import check_restrictions
from src.tools.common import ToolError
from src.tools.compute_allowance import compute_allowance
from src.tools.compute_duty_excise import compute_duty_excise
from src.tools.determine_exemption import determine_exemption
from src.tools.escalate_to_human import escalate_to_human
from src.tools.lookup_state_rule import lookup_state_rule
from src.tools.normalise_units import normalise_units
from src.tools.search_regulations import RegulationSearch, search_regulations
from src.tools.whatif_optimise import whatif_optimise

__all__ = [
    "RegulationSearch",
    "ToolError",
    "check_restrictions",
    "compute_allowance",
    "compute_duty_excise",
    "determine_exemption",
    "escalate_to_human",
    "lookup_state_rule",
    "normalise_units",
    "search_regulations",
    "whatif_optimise",
]
