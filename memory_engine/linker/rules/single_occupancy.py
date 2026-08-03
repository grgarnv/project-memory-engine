"""
Single-occupancy decisions.

Some questions admit exactly one current answer. "What do we use for
service-to-service authentication?" is one of them: a new SELECTED fact about
the same subject retires the old one rather than sitting beside it.

Direction is decided by timestamp, never by arrival order. See
memory_engine/linker/ordering.py.
"""
from __future__ import annotations

from memory_engine.linker.rules.base import AnalysisRule, record_supersession
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import MemoryDelta
from memory_engine.ontology import Predicate


class SingleOccupancyDecisionRule(AnalysisRule):
    name = "single_occupancy_decision"

    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for fact in delta.promoted_facts:
            if fact.predicate is not Predicate.SELECTED:
                continue
            for active in reader.get_active_facts_for_subject(fact.subject_ref):
                if (
                    active.id != fact.id
                    and active.predicate is Predicate.SELECTED
                    and active.object_ref != fact.object_ref
                ):
                    record_supersession(
                        reader, delta, fact.id, active.id,
                        "Single-occupancy decision supersession",
                    )
