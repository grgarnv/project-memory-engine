"""
Direct negation.

PROHIBITS and ALLOWS on the same pair contradict. Unlike a decision, there is
no single-occupancy assumption to resolve it, so memory records the conflict
and leaves both facts standing. Policy resolution is a human question.
"""
from __future__ import annotations

from memory_engine.linker.rules.base import AnalysisRule
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import ConflictEdge, MemoryDelta
from memory_engine.ontology import Predicate


class DirectNegationConflictRule(AnalysisRule):
    name = "direct_negation_conflict"

    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for fact in delta.promoted_facts:
            if fact.predicate not in (Predicate.PROHIBITS, Predicate.ALLOWS):
                continue
            opposite = (
                Predicate.ALLOWS if fact.predicate is Predicate.PROHIBITS
                else Predicate.PROHIBITS
            )
            for active in reader.get_active_facts_for_subject(fact.subject_ref):
                if active.predicate is opposite and active.object_ref == fact.object_ref:
                    delta.conflicts.append(
                        ConflictEdge(
                            fact_a_id=active.id,
                            fact_b_id=fact.id,
                            conflict_type="prohibits_allows_contradiction",
                            source_artifact_id=delta.artifact_id,
                        )
                    )
