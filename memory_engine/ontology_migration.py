"""
Ontology evolution.

RFC 002 specifies a versioned registry but not what happens to facts compiled
under an older version. Since memory is append-only, the two obvious answers are
both wrong:

  - Rewriting stored facts to the new predicate is a mutation, and destroys the
    ability to say what the project believed under the old taxonomy.
  - Leaving them alone silently splits the graph: `auth --selected--> X` and
    `auth --chose--> X` become unrelated edges.

The third answer, and the one taken here, is the same shape as entity aliasing:
a rename is a *declared equivalence*, applied at read time. Old facts stay
exactly as compiled. The resolver treats the old and new predicates as the same
question. Nothing is rewritten and nothing is lost.

A migration is therefore a statement about vocabulary, not an operation on data.
`plan()` reports what a version bump would affect before anyone commits to it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.ontology import OntologyVersion, Predicate


@dataclass(frozen=True, slots=True)
class PredicateMigration:
    """One predicate renamed or merged between ontology versions."""
    from_predicate: Predicate
    to_predicate: Predicate
    introduced_in: OntologyVersion
    rationale: str = ""


# Declared equivalences. Empty for V1_0 because nothing has been renamed yet;
# the machinery exists so that the first rename is a data change rather than an
# architecture change.
MIGRATIONS: tuple[PredicateMigration, ...] = ()


@dataclass
class MigrationImpact:
    """What a version bump would touch. Produced before anything is applied."""
    target_version: OntologyVersion
    affected_facts: int = 0
    affected_predicates: dict[str, int] = field(default_factory=dict)
    equivalences: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return self.affected_facts == 0


class OntologyMigrator:
    """
    Read-time predicate equivalence across ontology versions.

    Deliberately has no `apply()`. There is nothing to apply: facts are never
    rewritten, so a migration is fully described by the equivalence set plus a
    report of what it affects.
    """

    def __init__(self, migrations: tuple[PredicateMigration, ...] = MIGRATIONS):
        self.migrations = migrations
        self._forward: dict[Predicate, Predicate] = {
            m.from_predicate: m.to_predicate for m in migrations
        }
        self._reverse: dict[Predicate, set[Predicate]] = {}
        for old, new in self._forward.items():
            self._reverse.setdefault(new, set()).add(old)

    def canonical(self, predicate: Predicate) -> Predicate:
        """The current name for a predicate, following renames transitively."""
        seen = {predicate}
        current = predicate
        while current in self._forward:
            current = self._forward[current]
            if current in seen:  # a rename cycle is a taxonomy bug, not a loop
                break
            seen.add(current)
        return current

    def equivalents(self, predicate: Predicate) -> set[Predicate]:
        """Every predicate that asks the same question as this one."""
        canonical = self.canonical(predicate)
        found = {canonical, predicate}
        frontier = [canonical]
        while frontier:
            current = frontier.pop()
            for older in self._reverse.get(current, set()):
                if older not in found:
                    found.add(older)
                    frontier.append(older)
        return found

    def expand(self, predicates: tuple[Predicate, ...]) -> tuple[Predicate, ...]:
        """Widen a predicate filter to include every declared equivalent."""
        widened: list[Predicate] = []
        for predicate in predicates:
            for equivalent in sorted(self.equivalents(predicate), key=lambda p: p.value):
                if equivalent not in widened:
                    widened.append(equivalent)
        return tuple(widened)

    def plan(self, facts, target: OntologyVersion) -> MigrationImpact:
        """
        What changes if the project adopts `target`.

        Reports; never writes. Run this before a version bump, not after.
        """
        impact = MigrationImpact(target_version=target)
        relevant = {
            m.from_predicate: m for m in self.migrations
            if m.introduced_in is target
        }

        for fact in facts:
            migration = relevant.get(fact.predicate)
            if migration is None:
                continue
            impact.affected_facts += 1
            key = f"{migration.from_predicate.value} -> {migration.to_predicate.value}"
            impact.affected_predicates[key] = impact.affected_predicates.get(key, 0) + 1

        impact.equivalences = [
            (m.from_predicate.value, m.to_predicate.value) for m in relevant.values()
        ]

        if impact.is_noop:
            impact.notes.append(
                f"No stored fact uses a predicate renamed in {target.value}."
            )
        else:
            impact.notes.append(
                f"{impact.affected_facts} fact(s) use a renamed predicate. They are "
                f"NOT rewritten: the old and new names are treated as the same "
                f"question at read time, so history stays exactly as compiled."
            )
        return impact
