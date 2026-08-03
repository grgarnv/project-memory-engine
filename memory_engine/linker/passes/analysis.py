"""
Pass 3: Analysis.

Runs an ordered sequence of AnalysisRule plugins, then de-duplicates the edges
they produced. Two rules can legitimately reach the same conclusion - an
explicit "replace X with Y" and a single-occupancy decision often do - and
memory should record that once.

Rules run in a fixed order and are pure with respect to memory: they append
edges to the delta and touch nothing else.
"""
from __future__ import annotations

from memory_engine.linker.rules import DEFAULT_RULES, AnalysisRule
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import MemoryDelta


class AnalysisPipeline:
    def __init__(self, rules: list[AnalysisRule] | None = None):
        self.rules = rules if rules is not None else [rule() for rule in DEFAULT_RULES]

    def execute(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for rule in self.rules:
            rule.analyze(reader, delta)
        self._dedupe(delta)

    @staticmethod
    def _dedupe(delta: MemoryDelta) -> None:
        seen_s: set[tuple[str, str]] = set()
        supersessions = []
        for edge in delta.supersessions:
            key = (edge.superseding_fact_id, edge.superseded_fact_id)
            if key in seen_s:
                continue
            seen_s.add(key)
            supersessions.append(edge)
        delta.supersessions = supersessions

        seen_c: set[tuple[str, str, str]] = set()
        conflicts = []
        for edge in delta.conflicts:
            key = tuple(sorted((edge.fact_a_id, edge.fact_b_id))) + (edge.conflict_type,)
            if key in seen_c:
                continue
            seen_c.add(key)
            conflicts.append(edge)
        delta.conflicts = conflicts
