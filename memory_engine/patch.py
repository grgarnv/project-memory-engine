"""
MemoryPatch Linker & Persistent Memory Engine (Phase 2 Architecture)

This module implements the three-pass MemoryPatch Linker:
    Pass 1: BindingPass (Local Entities -> Global Entity IDs; $ARTIFACT_SELF -> ArtifactRef)
    Pass 2: PersistencePass (Compiler Facts -> PersistedFact + EvidenceRecord accumulation)
    Pass 3: AnalysisPipeline (Modular AnalysisRule passes for supersession & conflict detection)

It also provides `InMemoryProjectMemory` as an append-only reference temporal property graph.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from memory_engine.ir import CompiledArtifact, Entity, Fact, Relation, deterministic_id
from memory_engine.ontology import Predicate, EntityType, OntologyVersion


# ---------------------------------------------------------------------------
# Core Symbol & Reference Primitives
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class ArtifactRef:
    """
    Special linker reference indicating an assertion applies to the source artifact itself.

    Preserves ontology separation: an Artifact is a source of evidence/document,
    NOT a project domain concept Entity.
    """
    artifact_id: str


@dataclass(slots=True)
class GlobalEntityBinding:
    """Links an artifact-local entity reference to a persistent global entity ID."""
    local_canonical_name: str
    global_entity_id: str
    entity_type: EntityType = EntityType.UNKNOWN


# ---------------------------------------------------------------------------
# Persistent Graph Primitives (Evidence Model)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EvidenceRecord:
    """
    Represents one piece of artifact-level evidence supporting a PersistedFact.

    Enables: One PersistedFact -> Many EvidenceRecords.
    """
    id: str
    persisted_fact_id: str
    source_artifact_id: str
    source_fact_id: str
    confidence: float = 1.0
    supporting_statements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PersistedFact:
    """
    A fact edge accepted into long-term persistent memory, with stable identity.

    Stores subject/object as either a global entity ID string or ArtifactRef formatted string.
    """
    id: str
    subject_ref: str  # global_entity_id or "artifact:<id>"
    predicate: Predicate
    object_ref: str   # global_entity_id or literal string or "artifact:<id>"
    fact_type: str = "observation"
    confidence: float = 1.0


@dataclass(slots=True)
class SupersessionEdge:
    """Represents an explicit or structural supersession edge (Fact B overrides Fact A)."""
    superseding_fact_id: str
    superseded_fact_id: str
    reason: str = ""


@dataclass(slots=True)
class ConflictEdge:
    """Represents a contradiction between two assertions requiring policy review."""
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
    evidence_records: list[EvidenceRecord] = field(default_factory=list)
    supersessions: list[SupersessionEdge] = field(default_factory=list)
    conflicts: list[ConflictEdge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return (
            not self.bound_entities
            and not self.promoted_facts
            and not self.evidence_records
            and not self.supersessions
            and not self.conflicts
        )


# ---------------------------------------------------------------------------
# Memory Reader Contract
# ---------------------------------------------------------------------------

class MemoryReader(ABC):
    """Read-only snapshot interface to Persistent Memory."""

    @abstractmethod
    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        """Return the global entity ID if canonical_name or an alias is registered."""

    @abstractmethod
    def get_persisted_fact_by_id(self, fact_id: str) -> PersistedFact | None:
        """Return a PersistedFact by its deterministic ID if present."""

    @abstractmethod
    def find_existing_fact(self, subject_ref: str, predicate: Predicate, object_ref: str) -> PersistedFact | None:
        """Return an existing PersistedFact matching (subject_ref, predicate, object_ref)."""

    @abstractmethod
    def get_active_facts_for_subject(self, subject_ref: str) -> list[PersistedFact]:
        """Return all current (non-superseded) active facts for a subject."""


# ---------------------------------------------------------------------------
# Pass 1 — BindingPass
# ---------------------------------------------------------------------------

class BindingPass:
    """
    Pass 1 of Linker:
    - Binds local artifact entity mentions to global persistent Entity IDs.
    - Resolves $ARTIFACT_SELF / CURRENT_CHANGE to ArtifactRef(artifact_id).
    - Unresolved entities safely remain unresolved. Zero semantic reasoning.
    """

    def bind(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> dict[str, Any]:
        entity_bindings: dict[str, str] = {}  # local_name.lower() -> global_id
        bound_list: list[GlobalEntityBinding] = []

        for entity in compiled_artifact.entities:
            key = entity.canonical_name.lower()
            global_id = reader.find_entity_by_canonical_name(entity.canonical_name)
            if not global_id:
                # Assign deterministic global entity ID
                global_id = deterministic_id("entity", entity.entity_type.value, key)

            entity_bindings[key] = global_id
            bound_list.append(
                GlobalEntityBinding(
                    local_canonical_name=entity.canonical_name,
                    global_entity_id=global_id,
                    entity_type=entity.entity_type,
                )
            )

        return {
            "entity_bindings": entity_bindings,
            "bound_list": bound_list,
            "artifact_ref": ArtifactRef(compiled_artifact.artifact.id),
        }


# ---------------------------------------------------------------------------
# Pass 2 — PersistencePass
# ---------------------------------------------------------------------------

class PersistencePass:
    """
    Pass 2 of Linker:
    - Promotes compiler Facts to content-addressed PersistedFact nodes.
    - Accumulates EvidenceRecord entries when multiple artifacts support the same fact.
    - Performs O(1) deduplication.
    """

    def persist(
        self,
        reader: MemoryReader,
        compiled_artifact: CompiledArtifact,
        binding_result: dict[str, Any],
    ) -> MemoryDelta:
        delta = MemoryDelta(
            artifact_id=compiled_artifact.artifact.id,
            bound_entities=binding_result["bound_list"],
        )

        entity_map = binding_result["entity_bindings"]
        art_ref: ArtifactRef = binding_result["artifact_ref"]

        for fact in compiled_artifact.facts:
            # Resolve subject
            if fact.subject.lower() in ("current change", "$artifact_self"):
                subject_ref = f"artifact:{art_ref.artifact_id}"
            else:
                subject_ref = entity_map.get(fact.subject.lower(), fact.subject)

            # Resolve object
            object_ref = entity_map.get(fact.object.lower(), fact.object)

            # Generate deterministic content-addressed fact ID
            pfact_id = deterministic_id("fact", subject_ref, fact.predicate.value, object_ref)

            # Check if fact already exists in memory or in current delta
            existing_pfact = reader.find_existing_fact(subject_ref, fact.predicate, object_ref)

            if existing_pfact:
                target_fact_id = existing_pfact.id
            else:
                # Create new PersistedFact node
                new_pfact = PersistedFact(
                    id=pfact_id,
                    subject_ref=subject_ref,
                    predicate=fact.predicate,
                    object_ref=object_ref,
                    confidence=1.0,
                )
                delta.promoted_facts.append(new_pfact)
                target_fact_id = pfact_id

            # Create EvidenceRecord
            evidence_id = deterministic_id("evidence", art_ref.artifact_id, fact.id)
            evidence = EvidenceRecord(
                id=evidence_id,
                persisted_fact_id=target_fact_id,
                source_artifact_id=art_ref.artifact_id,
                source_fact_id=fact.id,
                confidence=1.0,
                supporting_statements=list(fact.supporting_statements),
            )
            delta.evidence_records.append(evidence)

        return delta


# ---------------------------------------------------------------------------
# Pass 3 — AnalysisRule Pipeline & Rules
# ---------------------------------------------------------------------------

class AnalysisRule(ABC):
    """Abstract interface for independent analysis rules executed in Pass 3."""

    @abstractmethod
    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        """Analyze memory state + delta and append supersessions/conflicts to delta."""


class ExplicitDeprecationRule(AnalysisRule):
    """Rule: Detects explicit REPLACED_BY or DEPRECATED predicates."""

    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for pfact in delta.promoted_facts:
            if pfact.predicate in (Predicate.REPLACED_BY, Predicate.DEPRECATED):
                active_facts = reader.get_active_facts_for_subject(pfact.subject_ref)
                for active in active_facts:
                    if active.id != pfact.id and active.object_ref != pfact.object_ref:
                        delta.supersessions.append(
                            SupersessionEdge(
                                superseding_fact_id=pfact.id,
                                superseded_fact_id=active.id,
                                reason=f"Explicit {pfact.predicate.value} declaration",
                            )
                        )


class SingleOccupancyDecisionRule(AnalysisRule):
    """Rule: Detects SELECTED decision overrides on the same subject."""

    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for pfact in delta.promoted_facts:
            if pfact.predicate == Predicate.SELECTED:
                active_facts = reader.get_active_facts_for_subject(pfact.subject_ref)
                for active in active_facts:
                    if (
                        active.id != pfact.id
                        and active.predicate == Predicate.SELECTED
                        and active.object_ref != pfact.object_ref
                    ):
                        delta.supersessions.append(
                            SupersessionEdge(
                                superseding_fact_id=pfact.id,
                                superseded_fact_id=active.id,
                                reason="Single-occupancy decision supersession",
                            )
                        )


class DirectNegationConflictRule(AnalysisRule):
    """Rule: Detects direct contradiction facts (PROHIBITS vs ALLOWS)."""

    def analyze(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for pfact in delta.promoted_facts:
            if pfact.predicate in (Predicate.PROHIBITS, Predicate.ALLOWS):
                opposite = Predicate.ALLOWS if pfact.predicate == Predicate.PROHIBITS else Predicate.PROHIBITS
                active_facts = reader.get_active_facts_for_subject(pfact.subject_ref)
                for active in active_facts:
                    if active.predicate == opposite and active.object_ref == pfact.object_ref:
                        delta.conflicts.append(
                            ConflictEdge(
                                fact_a_id=active.id,
                                fact_b_id=pfact.id,
                                conflict_type="prohibits_allows_contradiction",
                            )
                        )


class AnalysisPipeline:
    """Pipeline manager executing a sequence of AnalysisRule plugins."""

    def __init__(self, rules: list[AnalysisRule] | None = None):
        self.rules = rules or [
            ExplicitDeprecationRule(),
            SingleOccupancyDecisionRule(),
            DirectNegationConflictRule(),
        ]

    def execute(self, reader: MemoryReader, delta: MemoryDelta) -> None:
        for rule in self.rules:
            rule.analyze(reader, delta)


# ---------------------------------------------------------------------------
# Linker Implementation: ThreePassMemoryPatchLinker
# ---------------------------------------------------------------------------

class MemoryPatchLinker(ABC):
    """Abstract contract for MemoryPatch linkers."""

    @abstractmethod
    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        """Execute cross-artifact symbol resolution, deduplication, and supersession linking."""


class ThreePassMemoryPatchLinker(MemoryPatchLinker):
    """
    Deterministic Three-Pass Linker:
    - Pass 1: BindingPass
    - Pass 2: PersistencePass
    - Pass 3: AnalysisPipeline
    """

    def __init__(self, analysis_pipeline: AnalysisPipeline | None = None):
        self.binding_pass = BindingPass()
        self.persistence_pass = PersistencePass()
        self.analysis_pipeline = analysis_pipeline or AnalysisPipeline()

    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        # Pass 1: Binding
        binding_res = self.binding_pass.bind(reader, compiled_artifact)

        # Pass 2: Persistence & Evidence Accumulation
        delta = self.persistence_pass.persist(reader, compiled_artifact, binding_res)

        # Pass 3: Analysis
        self.analysis_pipeline.execute(reader, delta)

        return delta


# ---------------------------------------------------------------------------
# Reference Store: InMemoryProjectMemory
# ---------------------------------------------------------------------------

class InMemoryProjectMemory(MemoryReader):
    """
    Reference append-only in-memory storage engine.

    Implements MemoryReader snapshot queries and monotonic delta application (`apply_delta`).
    """

    def __init__(self):
        self.entities: dict[str, GlobalEntityBinding] = {}       # global_id -> binding
        self.canonical_index: dict[str, str] = {}               # canonical_name.lower() -> global_id
        self.facts: dict[str, PersistedFact] = {}                # fact_id -> PersistedFact
        self.evidence: list[EvidenceRecord] = []                # all evidence records
        self.superseded_fact_ids: set[str] = set()               # fact_ids overridden by supersessions
        self.supersessions: list[SupersessionEdge] = []
        self.conflicts: list[ConflictEdge] = []

    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        return self.canonical_index.get(canonical_name.lower())

    def get_persisted_fact_by_id(self, fact_id: str) -> PersistedFact | None:
        return self.facts.get(fact_id)

    def find_existing_fact(self, subject_ref: str, predicate: Predicate, object_ref: str) -> PersistedFact | None:
        for pfact in self.facts.values():
            if (
                pfact.subject_ref == subject_ref
                and pfact.predicate == predicate
                and pfact.object_ref == object_ref
            ):
                return pfact
        return None

    def get_active_facts_for_subject(self, subject_ref: str) -> list[PersistedFact]:
        return [
            f for f in self.facts.values()
            if f.subject_ref == subject_ref and f.id not in self.superseded_fact_ids
        ]

    def apply_delta(self, delta: MemoryDelta) -> None:
        """Apply a MemoryDelta package monotonically to the in-memory graph."""
        # 1. Store entity bindings
        for binding in delta.bound_entities:
            self.entities[binding.global_entity_id] = binding
            self.canonical_index[binding.local_canonical_name.lower()] = binding.global_entity_id

        # 2. Append facts
        for pfact in delta.promoted_facts:
            self.facts[pfact.id] = pfact

        # 3. Append evidence
        self.evidence.extend(delta.evidence_records)

        # 4. Append supersessions and update active state index
        for s_edge in delta.supersessions:
            self.supersessions.append(s_edge)
            self.superseded_fact_ids.add(s_edge.superseded_fact_id)

        # 5. Append conflicts
        self.conflicts.extend(delta.conflicts)
