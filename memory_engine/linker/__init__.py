"""
The linker: stateful integration of compiled artifacts into persistent memory.

Owns identity, evidence accumulation, entity binding, and historical evolution.
The compiler never does.
"""
from memory_engine.linker.linker import MemoryPatchLinker, ThreePassMemoryPatchLinker
from memory_engine.linker.ordering import Order, compare_assertions
from memory_engine.linker.passes import (
    AnalysisPipeline,
    BindingPass,
    PersistencePass,
    global_entity_id,
)
from memory_engine.linker.rules import (
    AnalysisRule,
    DirectNegationConflictRule,
    ExplicitDeprecationRule,
    SingleOccupancyDecisionRule,
)

__all__ = [
    "MemoryPatchLinker",
    "ThreePassMemoryPatchLinker",
    "BindingPass",
    "PersistencePass",
    "AnalysisPipeline",
    "global_entity_id",
    "AnalysisRule",
    "ExplicitDeprecationRule",
    "SingleOccupancyDecisionRule",
    "DirectNegationConflictRule",
    "Order",
    "compare_assertions",
]
