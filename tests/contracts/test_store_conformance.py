"""
Store conformance.

Every store runs this suite. SQLite is not allowed its own definition of
correct behaviour - if it diverges from the in-memory reference, this fails.

Written against the contracts in memory_engine.memory.contracts only. If a test
here needs a store's internals, the contract is missing something.
"""
from __future__ import annotations

import pytest

from memory_engine.memory.model import (
    ConflictEdge,
    EvidenceRecord,
    GlobalEntityBinding,
    MemoryDelta,
    PersistedFact,
    SupersessionEdge,
)
from memory_engine.ontology import EntityType, Predicate

E_AUTH = "entity_auth"
E_JWT = "entity_jwt"
E_OAUTH = "entity_oauth"

F_JWT = "fact_jwt"
F_OAUTH = "fact_oauth"


def _delta(**kwargs) -> MemoryDelta:
    base = dict(artifact_id="artifact_1", artifact_recorded_at="2024-01-01")
    base.update(kwargs)
    return MemoryDelta(**base)


def _seed(store) -> None:
    store.apply_delta(_delta(
        artifact_id="artifact_adr004",
        artifact_recorded_at="2023-01-11",
        bound_entities=[
            GlobalEntityBinding("service-to-service authentication", E_AUTH,
                                EntityType.CAPABILITY, ["auth"]),
            GlobalEntityBinding("JWT", E_JWT, EntityType.FRAMEWORK, []),
        ],
        promoted_facts=[
            PersistedFact(F_JWT, E_AUTH, Predicate.SELECTED, E_JWT, "decision"),
        ],
        evidence_records=[
            EvidenceRecord("ev1", F_JWT, "artifact_adr004", "f1", "adr",
                           "2023-01-11", 1.0, 1.0, ["s1"]),
        ],
    ))


def test_entity_lookup_by_name_and_alias(any_store):
    _seed(any_store)
    assert any_store.find_entity_by_canonical_name("JWT") == E_JWT
    assert any_store.find_entity_by_canonical_name("jwt") == E_JWT
    assert any_store.find_entity_by_canonical_name("auth") == E_AUTH
    assert any_store.find_entity_by_canonical_name("Kerberos") is None


def test_label_round_trip(any_store):
    _seed(any_store)
    assert any_store.label_for_ref(E_JWT) == "JWT"
    assert any_store.label_for_ref("some literal") == "some literal"


def test_find_existing_fact_matches_the_triple(any_store):
    _seed(any_store)
    found = any_store.find_existing_fact(E_AUTH, Predicate.SELECTED, E_JWT)
    assert found is not None and found.id == F_JWT
    assert any_store.find_existing_fact(E_AUTH, Predicate.USES, E_JWT) is None


def test_facts_mentioning_covers_both_positions(any_store):
    _seed(any_store)
    assert [f.id for f in any_store.facts_mentioning(E_JWT)] == [F_JWT]
    assert [f.id for f in any_store.facts_mentioning(E_AUTH)] == [F_JWT]


def test_active_facts_with_object_filters_by_predicate(any_store):
    _seed(any_store)
    assert any_store.get_active_facts_with_object(E_JWT, (Predicate.SELECTED,))
    assert not any_store.get_active_facts_with_object(E_JWT, (Predicate.USES,))


def test_evidence_accumulates_without_duplicating_the_fact(any_store):
    _seed(any_store)
    any_store.apply_delta(_delta(
        artifact_id="artifact_pr",
        artifact_recorded_at="2023-06-01",
        evidence_records=[
            EvidenceRecord("ev2", F_JWT, "artifact_pr", "f2", "pull_request",
                           "2023-06-01", 1.0, 0.8, []),
        ],
    ))
    assert len(any_store.evidence_for_fact(F_JWT)) == 2
    assert any_store.stats()["facts"] == 1


def test_latest_evidence_time_is_the_max(any_store):
    _seed(any_store)
    any_store.apply_delta(_delta(
        artifact_id="artifact_pr",
        artifact_recorded_at="2023-06-01",
        evidence_records=[
            EvidenceRecord("ev2", F_JWT, "artifact_pr", "f2", "pull_request",
                           "2023-06-01", 1.0, 0.8, []),
        ],
    ))
    assert any_store.latest_evidence_time(F_JWT) == "2023-06-01"
    assert any_store.latest_evidence_time("nonexistent") == ""


def test_supersession_marks_but_never_deletes(any_store):
    _seed(any_store)
    any_store.apply_delta(_delta(
        artifact_id="artifact_adr012",
        artifact_recorded_at="2024-05-02",
        bound_entities=[GlobalEntityBinding("OAuth2", E_OAUTH, EntityType.FRAMEWORK, [])],
        promoted_facts=[PersistedFact(F_OAUTH, E_AUTH, Predicate.SELECTED, E_OAUTH, "decision")],
        supersessions=[SupersessionEdge(F_OAUTH, F_JWT, "replaced", "artifact_adr012",
                                        "2024-05-02", "recorded_at")],
    ))
    assert any_store.is_superseded(F_JWT)
    assert any_store.get_fact(F_JWT) is not None, "history must survive supersession"
    assert [f.id for f in any_store.get_active_facts_for_subject(E_AUTH)] == [F_OAUTH]


def test_supersession_edges_are_traversable_both_ways(any_store):
    _seed(any_store)
    any_store.apply_delta(_delta(
        artifact_id="artifact_adr012",
        promoted_facts=[PersistedFact(F_OAUTH, E_AUTH, Predicate.SELECTED, E_OAUTH)],
        supersessions=[SupersessionEdge(F_OAUTH, F_JWT, "replaced", "artifact_adr012")],
    ))
    assert any_store.supersession_edges_retiring(F_JWT)[0].superseding_fact_id == F_OAUTH
    assert any_store.supersession_edges_caused_by(F_OAUTH)[0].superseded_fact_id == F_JWT


def test_conflicts_are_retrievable_from_either_side(any_store):
    _seed(any_store)
    any_store.apply_delta(_delta(
        promoted_facts=[PersistedFact(F_OAUTH, E_AUTH, Predicate.SELECTED, E_OAUTH)],
        conflicts=[ConflictEdge(F_JWT, F_OAUTH, "simultaneous_incompatible_assertions")],
    ))
    assert any_store.conflicts_involving(F_JWT)
    assert any_store.conflicts_involving(F_OAUTH)


def test_replaying_a_delta_is_idempotent(any_store):
    """Ingestion should converge, not accumulate artefacts of how it was run."""
    _seed(any_store)
    before = any_store.stats()
    _seed(any_store)
    assert any_store.stats() == before
