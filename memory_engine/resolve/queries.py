"""
Queries.

Single-entity lookup answers "what do we believe about X". Real questions about
a codebase are usually shaped differently: what changed, what breaks if this
goes away, what does memory hold that nothing supports.

Everything here is derived from stored values by deterministic traversal. No
query invents an ordering, a threshold, or a ranking that memory did not
already contain — a caller supplying a threshold is making a judgement, and the
threshold is theirs, not the engine's.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.memory.contracts import BeliefReader
from memory_engine.memory.model import is_artifact_ref
from memory_engine.ontology import Predicate
from memory_engine.resolve.identity import IdentityResolver
from memory_engine.resolve.resolver import BeliefResolver

# Predicates that mean "this thing relies on that thing".
_DEPENDENCY_PREDICATES = (
    Predicate.USES, Predicate.DEPENDS_ON, Predicate.REQUIRES,
    Predicate.IMPORTS, Predicate.CALLS, Predicate.CONTAINS,
)


@dataclass(slots=True)
class TimelineEntry:
    when: str
    fact_id: str
    statement: str
    artifact_id: str
    artifact_type: str
    event: str  # "asserted" | "retired"

    @property
    def is_dated(self) -> bool:
        return bool(self.when)


@dataclass(slots=True)
class Dependent:
    label: str
    ref: str
    predicate: Predicate
    support: float
    evidence_count: int


@dataclass
class HealthReport:
    """
    What memory itself says is shaky. Diagnostics for the knowledge base, not
    for the project.
    """
    total_facts: int = 0
    active_facts: int = 0
    undated_facts: int = 0
    single_source_facts: int = 0
    ingestion_ordered_supersessions: int = 0
    open_conflicts: int = 0
    unresolved_literals: int = 0
    notes: list[str] = field(default_factory=list)


class ProjectQueries:
    """Read-only queries over persistent memory."""

    def __init__(self, reader: BeliefReader):
        self.reader = reader
        self.identity = IdentityResolver(reader)
        self.resolver = BeliefResolver(reader)

    # -- timeline -----------------------------------------------------------

    def timeline(self, entity_name: str) -> list[TimelineEntry]:
        """
        Everything memory recorded about a concept, in the order it happened.

        Undated entries sort last rather than first: an unknown date is not
        "the beginning of time", and putting it there would silently invent a
        chronology.
        """
        ref = self.reader.resolve_ref(entity_name)
        if ref is None:
            return []

        entries: list[TimelineEntry] = []
        for member in self.identity.equivalence_class(ref).refs:
            for fact in self.reader.facts_mentioning(member):
                statement = (
                    f"{self.reader.label_for_ref(fact.subject_ref)} "
                    f"--{fact.predicate.value}--> "
                    f"{self.reader.label_for_ref(fact.object_ref)}"
                )
                for ev in self.reader.evidence_for_fact(fact.id):
                    entries.append(TimelineEntry(
                        when=ev.recorded_at,
                        fact_id=fact.id,
                        statement=statement,
                        artifact_id=ev.source_artifact_id,
                        artifact_type=ev.artifact_type,
                        event="asserted",
                    ))
                for edge in self.reader.supersession_edges_retiring(fact.id):
                    entries.append(TimelineEntry(
                        when=edge.recorded_at,
                        fact_id=fact.id,
                        statement=statement,
                        artifact_id=edge.source_artifact_id,
                        artifact_type="",
                        event="retired",
                    ))

        seen: set[tuple] = set()
        unique = []
        for entry in entries:
            key = (entry.when, entry.fact_id, entry.event, entry.artifact_id)
            if key not in seen:
                seen.add(key)
                unique.append(entry)

        unique.sort(key=lambda e: (e.when == "", e.when, e.fact_id, e.event))
        return unique

    # -- impact -------------------------------------------------------------

    def dependents(self, entity_name: str) -> list[Dependent]:
        """
        What currently relies on this concept — "what breaks if we remove X".

        Only active facts: something that depended on X until a superseded
        decision is not a dependent now, and reporting it would overstate blast
        radius.
        """
        ref = self.reader.resolve_ref(entity_name)
        if ref is None:
            return []

        found: dict[str, Dependent] = {}
        for member in self.identity.equivalence_class(ref).refs:
            for fact in self.reader.facts_mentioning(member):
                if fact.object_ref != member:
                    continue
                if fact.predicate not in _DEPENDENCY_PREDICATES:
                    continue
                if self.reader.is_superseded(fact.id):
                    continue
                if is_artifact_ref(fact.subject_ref):
                    continue

                evidence = self.reader.evidence_for_fact(fact.id)
                found[fact.id] = Dependent(
                    label=self.reader.label_for_ref(fact.subject_ref),
                    ref=fact.subject_ref,
                    predicate=fact.predicate,
                    support=round(sum(e.weight for e in evidence), 6),
                    evidence_count=len(evidence),
                )

        return sorted(found.values(), key=lambda d: (-d.support, d.label))

    # -- decisions ----------------------------------------------------------

    def decisions(self, facts) -> list[tuple[str, str, bool]]:
        """Every recorded decision as (subject, object, is_current)."""
        out = []
        for fact in facts:
            if fact.predicate is not Predicate.SELECTED:
                continue
            out.append((
                self.reader.label_for_ref(fact.subject_ref),
                self.reader.label_for_ref(fact.object_ref),
                not self.reader.is_superseded(fact.id),
            ))
        return sorted(out)

    # -- health -------------------------------------------------------------

    def health(self, all_facts) -> HealthReport:
        """
        Where this knowledge base is weak.

        A belief resting on one undated commit message is not the same as one
        resting on three dated ADRs, and a memory that cannot tell you which is
        which is not much of a memory.
        """
        report = HealthReport()
        for fact in all_facts:
            report.total_facts += 1
            superseded = self.reader.is_superseded(fact.id)
            if not superseded:
                report.active_facts += 1

            evidence = self.reader.evidence_for_fact(fact.id)
            if len(evidence) == 1 and not superseded:
                report.single_source_facts += 1
            if not any(e.recorded_at for e in evidence):
                report.undated_facts += 1

            for edge in self.reader.supersession_edges_retiring(fact.id):
                if edge.basis == "ingestion_order":
                    report.ingestion_ordered_supersessions += 1

            report.open_conflicts += len(self.reader.conflicts_involving(fact.id))

            for ref in (fact.subject_ref, fact.object_ref):
                if not ref.startswith("entity_") and not is_artifact_ref(ref):
                    report.unresolved_literals += 1

        report.open_conflicts //= 2  # each conflict is seen from both sides

        if report.ingestion_ordered_supersessions:
            report.notes.append(
                f"{report.ingestion_ordered_supersessions} supersession(s) rest on "
                f"ingestion order. Re-importing those artifacts in a different "
                f"order could change what the project believes."
            )
        if report.single_source_facts:
            report.notes.append(
                f"{report.single_source_facts} active fact(s) have exactly one "
                f"supporting artifact."
            )
        if report.unresolved_literals:
            report.notes.append(
                f"{report.unresolved_literals} fact operand(s) never resolved to an "
                f"entity and are stored as literal text."
            )
        return report
