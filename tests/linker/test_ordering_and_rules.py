"""
Supersession semantics.

The defect this file exists for: memory carried no time, so replaying the same
artifacts in a different order inverted what the project believed. Append-only
memory was monotonic in content but not in meaning.
"""
import itertools

import pytest

from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.linker import Order, compare_assertions
from memory_engine.ontology import Predicate
from memory_engine.resolve import BeliefResolver
from memory_engine.store import InMemoryProjectMemory
from tests.conftest import make_artifact

AUTH = "service-to-service authentication"
JWT_DECISION = ("## Decision\n\nUse JWT for service-to-service authentication.\n", "2023-01-11")
OAUTH_DECISION = ("## Decision\n\nUse OAuth2 for service-to-service authentication.\n", "2024-05-02")


def _ingest(memory, pairs):
    ingestor = Ingestor(memory=memory)
    for content, when in pairs:
        ingestor.ingest(make_artifact(content, ArtifactType.ADR, when))
    return BeliefResolver(memory)


@pytest.mark.parametrize("incoming,stored,expected", [
    ("2024-05-02", "2023-01-11", Order.LATER),
    ("2023-01-11", "2024-05-02", Order.EARLIER),
    ("2024-05-02", "2024-05-02", Order.SIMULTANEOUS),
    ("", "2024-05-02", Order.UNKNOWN),
    ("2024-05-02", "", Order.UNKNOWN),
])
def test_assertion_ordering(incoming, stored, expected):
    assert compare_assertions(incoming, stored) is expected


def test_newer_decision_supersedes_older():
    resolver = _ingest(InMemoryProjectMemory(), [JWT_DECISION, OAUTH_DECISION])
    assert resolver.explain(AUTH).decision.object_label == "OAuth2"


def test_older_decision_arriving_late_does_not_win():
    """Backfill safety: importing an archive out of order must not rewrite belief."""
    resolver = _ingest(InMemoryProjectMemory(), [OAUTH_DECISION, JWT_DECISION])
    assert resolver.explain(AUTH).decision.object_label == "OAuth2"


def test_belief_is_invariant_across_every_ingestion_order():
    outcomes = set()
    for order in itertools.permutations([JWT_DECISION, OAUTH_DECISION]):
        belief = _ingest(InMemoryProjectMemory(), list(order)).explain(AUTH)
        outcomes.add((
            belief.decision.object_label,
            tuple(sorted(n.object_label for n in belief.history)),
        ))
    assert len(outcomes) == 1, f"ingestion order changed the answer: {outcomes}"


def test_supersession_records_its_basis_and_its_cause():
    memory = InMemoryProjectMemory()
    _ingest(memory, [JWT_DECISION, OAUTH_DECISION])
    edge = memory.supersessions[0]
    assert edge.basis == "recorded_at"
    assert edge.source_artifact_id, "an explanation must be able to name the artifact"
    assert edge.recorded_at


def test_undated_artifacts_fall_back_to_ingestion_order_and_say_so():
    memory = InMemoryProjectMemory()
    _ingest(memory, [(JWT_DECISION[0], ""), (OAUTH_DECISION[0], "")])
    assert memory.supersessions[0].basis == "ingestion_order"

    belief = BeliefResolver(memory).explain(AUTH)
    assert any("ingestion order" in d for d in belief.diagnostics)


def test_simultaneous_incompatible_decisions_become_a_conflict():
    """Memory records the disagreement rather than picking a winner."""
    memory = InMemoryProjectMemory()
    _ingest(memory, [(JWT_DECISION[0], "2024-05-02"), (OAUTH_DECISION[0], "2024-05-02")])
    assert memory.conflicts
    assert memory.conflicts[0].conflict_type == "simultaneous_incompatible_assertions"
    assert not memory.supersessions


def test_explicit_replacement_retires_the_named_decision():
    memory = InMemoryProjectMemory()
    _ingest(memory, [
        JWT_DECISION,
        ("## Decision\n\nReplace JWT with OAuth2.\n", "2024-05-02"),
    ])
    belief = BeliefResolver(memory).explain("JWT")
    assert any(n.object_label == "JWT" and not n.active for n in belief.history)


def test_history_is_never_deleted():
    memory = InMemoryProjectMemory()
    _ingest(memory, [JWT_DECISION, OAUTH_DECISION])
    jwt_facts = [
        f for f in memory.facts.values()
        if memory.label_for_ref(f.object_ref) == "JWT"
    ]
    assert jwt_facts, "superseded facts must remain queryable"
