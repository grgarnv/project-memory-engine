from memory_engine.linker.rules.base import AnalysisRule, record_supersession
from memory_engine.linker.rules.deprecation import ExplicitDeprecationRule
from memory_engine.linker.rules.negation import DirectNegationConflictRule
from memory_engine.linker.rules.single_occupancy import SingleOccupancyDecisionRule

DEFAULT_RULES = (
    ExplicitDeprecationRule,
    SingleOccupancyDecisionRule,
    DirectNegationConflictRule,
)

__all__ = [
    "AnalysisRule",
    "record_supersession",
    "ExplicitDeprecationRule",
    "SingleOccupancyDecisionRule",
    "DirectNegationConflictRule",
    "DEFAULT_RULES",
]
