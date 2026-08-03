"""
Explicit deprecation.

When an artifact says "replace JWT with OAuth2" or "JWT is deprecated", that is
a direct instruction about the graph, not something to be inferred. This rule
retires the decisions and usages that named the deprecated thing.
"""
from __future__ import annotations

from memory_engine.linker.rules.base import AnalysisRule, record_supersession
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import MemoryDelta
from memory_engine.ontology import Predicate

# Predicates that assert something is currently in use, and are therefore
# invalidated when that something is explicitly replaced.
_CURRENCY_PREDICATES = (Predicate.SELECTED, Predicate.USES, Predicate.DEPENDS_ON)


class ExplicitDeprecationRule(AnalysisRule):
    name = "explicit_deprecation"

    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for fact in delta.promoted_facts:
            if fact.predicate not in (Predicate.REPLACED_BY, Predicate.DEPRECATED):
                continue

            # `A replaced_by B` retires facts that name A as the current choice.
            retired_subject = fact.subject_ref
            for candidate in self._facts_naming(reader, retired_subject):
                if candidate.id == fact.id:
                    continue
                record_supersession(
                    reader, delta, fact.id, candidate.id,
                    f"Explicit {fact.predicate.value} declaration",
                )

    @staticmethod
    def _facts_naming(reader: MemoryReader, ref: str):
        """
        Active facts whose OBJECT is the deprecated thing, plus active facts
        about it as subject. Uses only MemoryReader queries - the linker does
        not get read-path privileges.
        """
        found = [
            f for f in reader.get_active_facts_for_subject(ref)
            if f.predicate in _CURRENCY_PREDICATES
        ]
        found.extend(reader.get_active_facts_with_object(ref, _CURRENCY_PREDICATES))
        return found
