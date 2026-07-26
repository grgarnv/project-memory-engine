"""
MemoryPatch Contracts (Phase 2 Linker Specifications)

This module defines the abstract contracts and data structures for the
MemoryPatch Linker layer. The Linker sits downstream of single-artifact compilation:

    CompiledArtifact + MemoryReader -> MemoryPatchLinker -> MemoryDelta

Compiler:  Stateless single-artifact knowledge extraction (Artifact -> CompiledArtifact).
Linker:    Stateful cross-artifact knowledge linking (CompiledArtifact -> MemoryDelta).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from memory_engine.ir import CompiledArtifact, Entity, Fact, Relation, deterministic_id
from memory_engine.ontology import Predicate, EntityType


@dataclass(slots=True)
class GlobalEntityBinding:
    """Links an artifact-local entity reference to a persistent global entity ID."""
    local_canonical_name: str
    global_entity_id: str
    entity_type: EntityType = EntityType.UNKNOWN


@dataclass(slots=True)
class PersistedFact:
    """A fact edge accepted into long-term persistent memory, with full provenance."""
    id: str
    subject_entity_id: str
    predicate: Predicate
    object_entity_id_or_literal: str
    source_artifact_id: str
    source_fact_id: str
    confidence: float = 1.0


@dataclass(slots=True)
class SupersessionEdge:
    """Represents an explicit or structural supersession edge (Fact B overrides Fact A)."""
    superseding_fact_id: str
    superseded_fact_id: str
    reason: str = ""


@dataclass(slots=True)
class ConflictEdge:
    """Represents a contradiction between two assertions that requires human or policy review."""
    fact_a_id: str
    fact_b_id: str
    conflict_type: str = "contradictory_assertion"


@dataclass
class MemoryDelta:
    """
    Immutable append-only delta package emitted by the MemoryPatch linker.

    Contains NO deletion operations. Invalidation is expressed purely via
    `supersessions` edges.
    """
    artifact_id: str
    bound_entities: list[GlobalEntityBinding] = field(default_factory=list)
    promoted_facts: list[PersistedFact] = field(default_factory=list)
    supersessions: list[SupersessionEdge] = field(default_factory=list)
    conflicts: list[ConflictEdge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return (
            not self.bound_entities
            and not self.promoted_facts
            and not self.supersessions
            and not self.conflicts
        )


class MemoryReader(ABC):
    """
    Read-only snapshot interface to Persistent Memory.

    Passed into MemoryPatchLinker to enable symbol resolution and duplicate
    checking without allowing the Linker to mutate the underlying storage directly.
    """

    @abstractmethod
    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        """Return the global entity ID if canonical_name or an alias is registered."""

    @abstractmethod
    def get_active_facts_for_entity(self, entity_id: str) -> list[PersistedFact]:
        """Return all current (non-superseded) active facts involving entity_id."""

    @abstractmethod
    def fact_exists(self, subject_id: str, predicate: Predicate, object_id_or_literal: str) -> bool:
        """Check if an identical assertion already exists in persistent memory."""


class MemoryPatchLinker(ABC):
    """
    Abstract contract for MemoryPatch linkers.

    Consumes a single CompiledArtifact and a MemoryReader snapshot, producing an
    immutable MemoryDelta to append to project memory.
    """

    @abstractmethod
    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        """Execute cross-artifact symbol resolution, deduplication, and supersession linking."""
