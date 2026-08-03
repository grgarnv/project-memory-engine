"""
In-memory reference store.

The behavioural specification for every other store. `tests/contracts/` runs the
same conformance suite against this and against SQLite; if they diverge, the
suite fails.

Append-only: `apply_delta` adds, and nothing in this class removes or mutates
what is already there. Superseded facts stay in `facts` - they are marked, not
deleted, because "what did we believe in 2023 and why" has to remain answerable.
"""
from __future__ import annotations

from memory_engine.memory.contracts import ProjectMemory
from memory_engine.memory.model import (
    ARTIFACT_REF_PREFIX,
    ConflictEdge,
    EvidenceRecord,
    GlobalEntityBinding,
    MemoryDelta,
    PersistedFact,
    SupersessionEdge,
)
from memory_engine.ontology import Predicate


class InMemoryProjectMemory(ProjectMemory):
    def __init__(self) -> None:
        self.entities: dict[str, GlobalEntityBinding] = {}
        self.canonical_index: dict[str, str] = {}
        self.facts: dict[str, PersistedFact] = {}
        self.evidence: list[EvidenceRecord] = []
        self._evidence_ids: set[str] = set()
        self.supersessions: list[SupersessionEdge] = []
        self.conflicts: list[ConflictEdge] = []
        self.superseded_fact_ids: set[str] = set()
        self._supersession_keys: set[tuple[str, str]] = set()
        self._conflict_keys: set[tuple[str, ...]] = set()
        self.applied_artifacts: list[str] = []

    # -- MemoryReader -------------------------------------------------------

    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        return self.canonical_index.get(canonical_name.strip().lower())

    def get_persisted_fact_by_id(self, fact_id: str) -> PersistedFact | None:
        return self.facts.get(fact_id)

    def find_existing_fact(
        self, subject_ref: str, predicate: Predicate, object_ref: str
    ) -> PersistedFact | None:
        for fact in self.facts.values():
            if (
                fact.subject_ref == subject_ref
                and fact.predicate is predicate
                and fact.object_ref == object_ref
            ):
                return fact
        return None

    def get_active_facts_for_subject(self, subject_ref: str) -> list[PersistedFact]:
        return [
            f for f in self.facts.values()
            if f.subject_ref == subject_ref and f.id not in self.superseded_fact_ids
        ]

    def get_active_facts_with_object(
        self, object_ref: str, predicates: tuple[Predicate, ...] | None = None
    ) -> list[PersistedFact]:
        return [
            f for f in self.facts.values()
            if f.object_ref == object_ref
            and f.id not in self.superseded_fact_ids
            and (predicates is None or f.predicate in predicates)
        ]

    def latest_evidence_time(self, fact_id: str) -> str:
        times = [
            e.recorded_at for e in self.evidence
            if e.persisted_fact_id == fact_id and e.recorded_at
        ]
        return max(times) if times else ""

    # -- BeliefReader -------------------------------------------------------

    def facts_mentioning(self, ref: str) -> list[PersistedFact]:
        return [
            f for f in self.facts.values()
            if f.subject_ref == ref or f.object_ref == ref
        ]

    def get_fact(self, fact_id: str) -> PersistedFact | None:
        return self.facts.get(fact_id)

    def evidence_for_fact(self, fact_id: str) -> list[EvidenceRecord]:
        return [e for e in self.evidence if e.persisted_fact_id == fact_id]

    def supersession_edges_retiring(self, fact_id: str) -> list[SupersessionEdge]:
        return [s for s in self.supersessions if s.superseded_fact_id == fact_id]

    def supersession_edges_caused_by(self, fact_id: str) -> list[SupersessionEdge]:
        return [s for s in self.supersessions if s.superseding_fact_id == fact_id]

    def is_superseded(self, fact_id: str) -> bool:
        return fact_id in self.superseded_fact_ids

    def conflicts_involving(self, fact_id: str) -> list[ConflictEdge]:
        return [
            c for c in self.conflicts
            if c.fact_a_id == fact_id or c.fact_b_id == fact_id
        ]

    def resolve_ref(self, name: str) -> str | None:
        return self.find_entity_by_canonical_name(name)

    def label_for_ref(self, ref: str) -> str:
        binding = self.entities.get(ref)
        if binding:
            return binding.local_canonical_name
        if ref.startswith(ARTIFACT_REF_PREFIX):
            return f"<{ref[len(ARTIFACT_REF_PREFIX):][:12]}>"
        return ref

    # -- MemoryWriter -------------------------------------------------------

    def apply_delta(self, delta: MemoryDelta) -> None:
        for binding in delta.bound_entities:
            self.entities[binding.global_entity_id] = binding
            self.canonical_index[binding.local_canonical_name.strip().lower()] = (
                binding.global_entity_id
            )
            for alias in binding.aliases:
                self.canonical_index.setdefault(alias.strip().lower(), binding.global_entity_id)

        for fact in delta.promoted_facts:
            self.facts.setdefault(fact.id, fact)

        # Evidence is content-addressed by (artifact, source fact), so replaying
        # a delta adds nothing. Ingestion converges instead of accumulating.
        for record in delta.evidence_records:
            if record.id in self._evidence_ids:
                continue
            self._evidence_ids.add(record.id)
            self.evidence.append(record)

        for edge in delta.supersessions:
            key = (edge.superseding_fact_id, edge.superseded_fact_id)
            if key not in self._supersession_keys:
                self._supersession_keys.add(key)
                self.supersessions.append(edge)
            self.superseded_fact_ids.add(edge.superseded_fact_id)

        for conflict in delta.conflicts:
            key = tuple(sorted((conflict.fact_a_id, conflict.fact_b_id)))
            key = key + (conflict.conflict_type,)
            if key not in self._conflict_keys:
                self._conflict_keys.add(key)
                self.conflicts.append(conflict)

        if delta.artifact_id not in self.applied_artifacts:
            self.applied_artifacts.append(delta.artifact_id)

    # -- diagnostics --------------------------------------------------------

    def stats(self) -> dict[str, int]:
        return {
            "entities": len(self.entities),
            "facts": len(self.facts),
            "active_facts": len(self.facts) - len(self.superseded_fact_ids),
            "evidence": len(self.evidence),
            "supersessions": len(self.supersessions),
            "conflicts": len(self.conflicts),
            "artifacts": len(self.applied_artifacts),
        }
