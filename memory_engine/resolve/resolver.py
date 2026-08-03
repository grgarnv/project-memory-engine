"""
Belief resolution: the read path.

The compiler answers "what does this artifact assert?".
The linker answers "how does that assertion enter memory?".
This answers the question the project exists for:

    "What does the project currently believe about X, and why?"

    ProjectMemory
        |
        v
    BeliefResolver.explain(entity)
        |
        v
    ResolvedBelief
        current      active facts naming the entity, with accumulated evidence
        history      superseded facts, with the edge and artifact that retired them
        conflicts    contradictions memory declined to resolve
        diagnostics  why this answer is incomplete or fragile

Resolution is deterministic and performs no synthesis. It walks supersession
edges and evidence records the linker already wrote. Where memory does not
contain an answer, the resolver says so instead of inventing one.

The read-side non-goals mirror RFC 003's write-side non-goals:
  never calls an LLM, never does vector retrieval, never invents ranking
  heuristics at read time, never mutates memory, never fabricates a belief
  from an absence of evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memory_engine.memory.contracts import BeliefReader
from memory_engine.memory.model import ConflictEdge, PersistedFact
from memory_engine.ontology import Predicate
from memory_engine.resolve.identity import EquivalenceClass, IdentityResolver

# Predicates that express a decision, its rationale, or a structural commitment.
# Presentation order, not a ranking of truth.
DECISION_PREDICATES: tuple[Predicate, ...] = (
    Predicate.SELECTED,
    Predicate.REPLACED_BY,
    Predicate.DEPRECATED,
    Predicate.REJECTED,
    Predicate.USES,
    Predicate.DEPENDS_ON,
    Predicate.CONTAINS,
    Predicate.REQUIRES,
    Predicate.HAS_REASON,
    Predicate.HAS_TRADEOFF,
    Predicate.HAS_RISK,
    Predicate.HAS_BENEFIT,
)

_PREDICATE_ORDER = {p: i for i, p in enumerate(DECISION_PREDICATES)}


@dataclass(slots=True)
class EvidenceView:
    """One artifact's support for a fact, resolved for presentation."""
    artifact_id: str
    artifact_type: str
    recorded_at: str
    confidence: float
    authority: float
    supporting_statements: list[str] = field(default_factory=list)

    @property
    def weight(self) -> float:
        return round(self.confidence * self.authority, 6)


@dataclass(slots=True)
class BeliefNode:
    """One fact plus everything memory knows about its standing."""
    fact_id: str
    subject_label: str
    predicate: Predicate
    object_label: str
    active: bool
    evidence: list[EvidenceView] = field(default_factory=list)
    retired_by_fact_id: str | None = None
    retired_by_artifact_id: str = ""
    retirement_reason: str = ""
    retirement_basis: str = ""

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    @property
    def support(self) -> float:
        """
        Total evidential weight: sum of (claim confidence x artifact authority).

        Derived at read time from stored values, never stored. It says how much
        the project has committed to this belief - three ADRs outweigh one
        commit message - and it is explicitly NOT a probability of truth.
        """
        return round(sum(e.weight for e in self.evidence), 6)

    @property
    def last_asserted(self) -> str:
        times = [e.recorded_at for e in self.evidence if e.recorded_at]
        return max(times) if times else ""


@dataclass
class ResolvedBelief:
    query: str
    entity_ref: str | None
    identity: EquivalenceClass | None = None
    current: list[BeliefNode] = field(default_factory=list)
    history: list[BeliefNode] = field(default_factory=list)
    conflicts: list[ConflictEdge] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return bool(self.current or self.history)

    @property
    def decision(self) -> BeliefNode | None:
        """The single current decision, if this entity has one."""
        for node in self.current:
            if node.predicate is Predicate.SELECTED:
                return node
        return None


class BeliefResolver:
    """Deterministic read-path resolver over persistent project memory."""

    def __init__(self, reader: BeliefReader):
        self.reader = reader
        self.identity = IdentityResolver(reader)

    def explain(
        self,
        entity_name: str,
        predicates: tuple[Predicate, ...] | None = None,
    ) -> ResolvedBelief:
        result = ResolvedBelief(query=entity_name, entity_ref=None)

        ref = self.reader.resolve_ref(entity_name)
        if ref is None:
            result.diagnostics.append(
                f"No entity is registered under the name '{entity_name}'. Memory "
                f"cannot answer a question about a concept it never bound."
            )
            return result

        result.entity_ref = ref
        wanted = predicates or DECISION_PREDICATES

        # Ask about any name in the class and get the whole concept's answer.
        klass = self.identity.equivalence_class(ref)
        result.identity = klass

        facts = []
        seen_fact_ids: set[str] = set()
        for member in klass.refs:
            for fact in self.reader.facts_mentioning(member):
                if fact.id not in seen_fact_ids:
                    seen_fact_ids.add(fact.id)
                    facts.append(fact)

        # same_as edges are how the class was built; they are not an answer.
        facts = [f for f in facts if f.predicate is not Predicate.SAME_AS]

        if not facts:
            result.diagnostics.append(
                f"'{entity_name}' is bound (id={ref}) but appears in no persisted "
                f"fact: recognized as a name, never became knowledge."
            )
            return result

        relevant = [f for f in facts if f.predicate in wanted]
        if not relevant:
            seen = sorted({f.predicate.value for f in facts})
            result.diagnostics.append(
                f"'{entity_name}' appears only under predicates {seen}, none of "
                f"which express a decision or rationale."
            )
            return result

        seen_ids = set()
        for fact in sorted(relevant, key=self._sort_key):
            if fact.id in seen_ids:
                continue
            seen_ids.add(fact.id)
            node = self._build_node(fact)

            if node.active:
                result.current.append(node)
                # A current decision is only half an answer without what it
                # replaced. Walk the supersession edge forward, not just back.
                for edge in self.reader.supersession_edges_caused_by(fact.id):
                    retired = self.reader.get_fact(edge.superseded_fact_id)
                    if retired is not None and retired.id not in seen_ids:
                        seen_ids.add(retired.id)
                        result.history.append(self._build_node(retired))
            else:
                result.history.append(node)

            result.conflicts.extend(self.reader.conflicts_involving(fact.id))

        self._add_diagnostics(result)
        return result

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _sort_key(fact: PersistedFact) -> tuple[int, str]:
        return (_PREDICATE_ORDER.get(fact.predicate, 99), fact.object_ref)

    def _build_node(self, fact: PersistedFact) -> BeliefNode:
        superseded = self.reader.is_superseded(fact.id)
        node = BeliefNode(
            fact_id=fact.id,
            subject_label=self.reader.label_for_ref(fact.subject_ref),
            predicate=fact.predicate,
            object_label=self.reader.label_for_ref(fact.object_ref),
            active=not superseded,
            evidence=[
                EvidenceView(
                    artifact_id=e.source_artifact_id,
                    artifact_type=e.artifact_type,
                    recorded_at=e.recorded_at,
                    confidence=e.confidence,
                    authority=e.authority,
                    supporting_statements=list(e.supporting_statements),
                )
                for e in self.reader.evidence_for_fact(fact.id)
            ],
        )

        if superseded:
            edges = self.reader.supersession_edges_retiring(fact.id)
            if edges:
                edge = edges[0]
                node.retired_by_fact_id = edge.superseding_fact_id
                node.retired_by_artifact_id = edge.source_artifact_id
                node.retirement_reason = edge.reason
                node.retirement_basis = edge.basis
        return node

    def _add_diagnostics(self, result: ResolvedBelief) -> None:
        if result.current and not result.history:
            result.diagnostics.append(
                "No supersession edge touches this entity: memory holds a current "
                "position but no recorded history of what it replaced."
            )

        by_ingestion = [
            n for n in result.history if n.retirement_basis == "ingestion_order"
        ]
        if by_ingestion:
            result.diagnostics.append(
                f"{len(by_ingestion)} supersession(s) here were ordered by ingestion "
                f"order, not by artifact timestamps. Re-importing these artifacts in "
                f"a different order could invert this answer."
            )

        if result.identity and result.identity.is_merged:
            result.diagnostics.append(
                f"'{result.query}' resolved across {len(result.identity.refs)} names "
                f"asserted to be the same concept: "
                f"{', '.join(result.identity.labels)}."
            )
        if result.identity and result.identity.truncated:
            result.diagnostics.append(
                "The identity class hit the traversal bound; some equivalent "
                "names were not followed."
            )

        undated = [n for n in result.current if not n.last_asserted]
        if undated:
            result.diagnostics.append(
                f"{len(undated)} current fact(s) carry no timestamped evidence."
            )
