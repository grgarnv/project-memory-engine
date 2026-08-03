"""
Store contracts.

Two contracts, deliberately separate, because they serve opposite directions:

    MemoryReader  - what the LINKER needs to integrate a new artifact.
                    Minimal by design: subject-side lookups and existence checks.

    BeliefReader  - what the RESOLVER needs to answer a question.
                    Object-position lookups, superseded facts, supersession
                    edges in both directions, evidence by fact.

    MemoryWriter  - monotonic delta application.

A store implements all three. Keeping them separate keeps the linker from
growing a dependency on read-path queries and keeps the resolver from being
able to write.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from memory_engine.memory.model import (
    ConflictEdge,
    EvidenceRecord,
    MemoryDelta,
    PersistedFact,
    SupersessionEdge,
)
from memory_engine.ontology import Predicate


class MemoryReader(ABC):
    """Write-side snapshot queries. Everything the linker is allowed to know."""

    @abstractmethod
    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        """Global entity ID if this name or a registered alias is known."""

    @abstractmethod
    def get_persisted_fact_by_id(self, fact_id: str) -> PersistedFact | None:
        ...

    @abstractmethod
    def find_existing_fact(
        self, subject_ref: str, predicate: Predicate, object_ref: str
    ) -> PersistedFact | None:
        ...

    @abstractmethod
    def get_active_facts_for_subject(self, subject_ref: str) -> list[PersistedFact]:
        """Facts about this subject that no supersession edge has retired."""

    @abstractmethod
    def get_active_facts_with_object(
        self, object_ref: str, predicates: tuple[Predicate, ...] | None = None
    ) -> list[PersistedFact]:
        """
        Active facts naming this ref in OBJECT position, optionally filtered by
        predicate. Needed by the deprecation rule: "replace JWT with OAuth2"
        must retire `auth --selected--> JWT`, where JWT is the object.
        """

    @abstractmethod
    def latest_evidence_time(self, fact_id: str) -> str:
        """
        Most recent `recorded_at` among this fact's evidence, or "" if none of
        its evidence is timestamped. The ordering input for supersession.
        """


class BeliefReader(ABC):
    """Read-side queries. Everything the resolver needs and nothing that writes."""

    @abstractmethod
    def facts_mentioning(self, ref: str) -> list[PersistedFact]:
        """Facts with this ref in subject OR object position."""

    @abstractmethod
    def get_fact(self, fact_id: str) -> PersistedFact | None:
        ...

    @abstractmethod
    def evidence_for_fact(self, fact_id: str) -> list[EvidenceRecord]:
        ...

    @abstractmethod
    def supersession_edges_retiring(self, fact_id: str) -> list[SupersessionEdge]:
        """Edges where this fact is the one being retired."""

    @abstractmethod
    def supersession_edges_caused_by(self, fact_id: str) -> list[SupersessionEdge]:
        """Edges where this fact is the one doing the retiring."""

    @abstractmethod
    def is_superseded(self, fact_id: str) -> bool:
        ...

    @abstractmethod
    def conflicts_involving(self, fact_id: str) -> list[ConflictEdge]:
        ...

    @abstractmethod
    def resolve_ref(self, name: str) -> str | None:
        """Map a human-typed name to a global entity ID, if one is bound."""

    @abstractmethod
    def label_for_ref(self, ref: str) -> str:
        """Human-readable label for an entity ID, artifact ref, or literal."""


class MemoryWriter(ABC):
    """Monotonic application of linker output. No delete, no update."""

    @abstractmethod
    def apply_delta(self, delta: MemoryDelta) -> None:
        ...


class ProjectMemory(MemoryReader, BeliefReader, MemoryWriter, ABC):
    """A complete store. Both directions plus writes."""

    @abstractmethod
    def stats(self) -> dict[str, int]:
        """Counts by kind. Diagnostics only; never used in resolution."""
