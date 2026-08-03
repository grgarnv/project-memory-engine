"""
Identity resolution.

`API Gateway`, `the gateway`, and `APIGW` are three content-addressed entity IDs
in a store where IDs can never be rewritten. Merging them by mutation is not
available and would not be desirable if it were: deciding two names denote one
concept is a claim about the project, and claims belong in memory with evidence
attached.

So a merge is an assertion. `A --same_as--> B` is an ordinary `PersistedFact`,
carrying evidence like any other, superseded like any other if someone later
asserts the two were never the same thing. Resolution happens at read time by
walking the equivalence class.

Consequences worth being explicit about:

  - The class is computed over ACTIVE same_as facts only. Retracting a merge is
    a supersession, not a deletion, and history stays answerable.
  - Traversal is bounded and cycle-safe. `A same_as B`, `B same_as A`, and
    longer loops are normal in an append-only edge set, not corruption.
  - The class has a deterministic canonical member so two runs label an answer
    identically. Canonical choice is by name, never by insertion order.
  - This deliberately does NOT run inside the linker. Binding stays a
    zero-reasoning pass; equivalence is a read-time interpretation of evidence,
    and moving it into the write path would bake one interpretation into
    storage permanently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.memory.contracts import BeliefReader
from memory_engine.ontology import Predicate

# A pathological corpus should degrade, not hang.
MAX_CLASS_SIZE = 64


@dataclass(slots=True)
class EquivalenceClass:
    """A set of entity refs the project has asserted are one concept."""
    canonical_ref: str
    refs: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def canonical_label(self) -> str:
        return self.labels[0] if self.labels else self.canonical_ref

    @property
    def is_merged(self) -> bool:
        return len(self.refs) > 1

    @property
    def alternate_labels(self) -> list[str]:
        return self.labels[1:]


class IdentityResolver:
    """Walks active same_as edges to produce a deterministic equivalence class."""

    def __init__(self, reader: BeliefReader):
        self.reader = reader

    def equivalence_class(self, ref: str) -> EquivalenceClass:
        members: set[str] = {ref}
        frontier = [ref]
        truncated = False

        while frontier:
            current = frontier.pop()
            for fact in self.reader.facts_mentioning(current):
                if fact.predicate is not Predicate.SAME_AS:
                    continue
                if self.reader.is_superseded(fact.id):
                    continue  # a retracted merge is not a merge
                for candidate in (fact.subject_ref, fact.object_ref):
                    if candidate in members:
                        continue
                    if len(members) >= MAX_CLASS_SIZE:
                        truncated = True
                        continue
                    members.add(candidate)
                    frontier.append(candidate)

        ordered = self._order(members)
        return EquivalenceClass(
            canonical_ref=ordered[0],
            refs=ordered,
            labels=[self.reader.label_for_ref(r) for r in ordered],
            truncated=truncated,
        )

    def _order(self, members: set[str]) -> list[str]:
        """
        Canonical member first, then the rest alphabetically.

        The canonical name is the longest one, because the longest is almost
        always the most specific: "service-to-service authentication" says more
        than "auth". Ties break lexicographically. Nothing here depends on
        insertion order, so two runs over the same memory agree.
        """
        labelled = [(self.reader.label_for_ref(ref), ref) for ref in members]
        labelled.sort(key=lambda pair: (-len(pair[0]), pair[0], pair[1]))
        return [ref for _, ref in labelled]
