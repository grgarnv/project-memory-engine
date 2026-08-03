"""
Persistent memory schema.

This is the spine of the system: the linker writes these types, the resolver
reads them, and every store implements them. Neither side depends on the other -
both depend on this module.

    PersistedFact    a (subject, predicate, object) edge with stable identity
    EvidenceRecord   one artifact's support for a PersistedFact (many per fact)
    SupersessionEdge fact B retires fact A, attributed to the artifact that did it
    ConflictEdge     two assertions that contradict and were not resolvable
    MemoryDelta      the append-only package a linker emits for one artifact

Nothing here is ever mutated or deleted. Invalidation is expressed by adding a
SupersessionEdge, never by changing or removing a fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.ontology import EntityType, Predicate

# Refs are strings so a fact can point at three different kinds of thing:
#   "entity_<hash>"    a domain concept
#   "artifact:<id>"    the source document itself (see ArtifactRef)
#   anything else      an unresolved literal, kept verbatim rather than guessed
ARTIFACT_REF_PREFIX = "artifact:"


@dataclass(slots=True, frozen=True)
class ArtifactRef:
    """
    A reference to the source artifact itself.

    Preserves ontology separation: an Artifact is a source of evidence, not a
    project domain concept. "This PR describes X" is an artifact-level assertion;
    "the gateway uses OAuth2" is a domain assertion. They must not share an
    identity space.
    """
    artifact_id: str

    def as_ref(self) -> str:
        return f"{ARTIFACT_REF_PREFIX}{self.artifact_id}"


def is_artifact_ref(ref: str) -> bool:
    return ref.startswith(ARTIFACT_REF_PREFIX)


@dataclass(slots=True)
class GlobalEntityBinding:
    """Links an artifact-local entity mention to a persistent global entity ID."""
    local_canonical_name: str
    global_entity_id: str
    entity_type: EntityType = EntityType.UNKNOWN
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceRecord:
    """
    One artifact's support for one PersistedFact.

    Many evidence records accumulate under a single fact - this is the core
    idea: knowledge is accumulated evidence, not a document that was retrieved.

    `recorded_at` and `authority` exist so downstream resolution can weigh
    evidence without inventing heuristics at read time. `confidence` is carried
    through from the compiler's Claim, not hardcoded.
    """
    id: str
    persisted_fact_id: str
    source_artifact_id: str
    source_fact_id: str
    artifact_type: str = "document"
    recorded_at: str = ""
    confidence: float = 1.0
    authority: float = 0.5
    supporting_statements: list[str] = field(default_factory=list)

    @property
    def weight(self) -> float:
        """Combined evidential weight. Deterministic, derived, never stored."""
        return round(self.confidence * self.authority, 6)


@dataclass(slots=True)
class PersistedFact:
    """
    A fact edge in long-term memory, content-addressed by (subject, predicate, object).

    Immutable once written. It carries no timestamp of its own: a fact is not an
    event, it is a claim about the world that artifacts support at points in
    time. Time lives on EvidenceRecord.
    """
    id: str
    subject_ref: str
    predicate: Predicate
    object_ref: str
    fact_type: str = "observation"

    @property
    def is_artifact_scoped(self) -> bool:
        return is_artifact_ref(self.subject_ref)


@dataclass(slots=True)
class SupersessionEdge:
    """
    Fact B retires fact A.

    `source_artifact_id` records WHICH artifact caused the retirement, so an
    explanation can name it. Without it, memory knows a decision was replaced
    but not by what.

    `basis` records how the ordering was established - "recorded_at" when the
    artifacts carry timestamps, "ingestion_order" when they do not. A memory
    full of ingestion_order supersessions is a memory whose beliefs depend on
    replay order, and the resolver reports that.
    """
    superseding_fact_id: str
    superseded_fact_id: str
    reason: str = ""
    source_artifact_id: str = ""
    recorded_at: str = ""
    basis: str = "ingestion_order"


@dataclass(slots=True)
class ConflictEdge:
    """Two assertions that contradict and could not be ordered or resolved."""
    fact_a_id: str
    fact_b_id: str
    conflict_type: str = "contradictory_assertion"
    source_artifact_id: str = ""


@dataclass
class MemoryDelta:
    """
    The append-only package emitted by the linker for one artifact.

    Contains no deletion operations of any kind. Invalidation travels as
    supersession edges.
    """
    artifact_id: str
    artifact_recorded_at: str = ""
    bound_entities: list[GlobalEntityBinding] = field(default_factory=list)
    promoted_facts: list[PersistedFact] = field(default_factory=list)
    evidence_records: list[EvidenceRecord] = field(default_factory=list)
    supersessions: list[SupersessionEdge] = field(default_factory=list)
    conflicts: list[ConflictEdge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.bound_entities
            or self.promoted_facts
            or self.evidence_records
            or self.supersessions
            or self.conflicts
        )
