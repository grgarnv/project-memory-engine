"""
The read path.

"Why do we use OAuth2 instead of JWT?" is the question the project exists to
answer. These tests are the specification of what a good answer contains.
"""
import pytest

from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.ontology import Predicate
from memory_engine.resolve import BeliefResolver, render
from memory_engine.store import InMemoryProjectMemory
from tests.conftest import make_artifact

AUTH = "service-to-service authentication"

CORPUS = [
    ("## Decision\n\nUse JWT for service-to-service authentication.\n",
     ArtifactType.ADR, "2023-01-11"),
    ("## Decision\n\nUse OAuth2 for service-to-service authentication.\n",
     ArtifactType.ADR, "2024-05-02"),
    ("Migrate the API Gateway to OAuth2.\n\nReason:\n\n"
     "Use OAuth2 for service-to-service authentication.\n",
     ArtifactType.PR, "2024-05-20"),
]


@pytest.fixture
def resolver():
    memory = InMemoryProjectMemory()
    ingestor = Ingestor(memory=memory)
    for content, atype, when in CORPUS:
        ingestor.ingest(make_artifact(content, atype, when))
    return BeliefResolver(memory)


def test_current_decision_is_resolved(resolver):
    assert resolver.explain(AUTH).decision.object_label == "OAuth2"


def test_superseded_decision_is_retained_with_attribution(resolver):
    belief = resolver.explain(AUTH)
    retired = next(n for n in belief.history if n.object_label == "JWT")
    assert retired.retired_by_fact_id == belief.decision.fact_id
    assert retired.retired_by_artifact_id, "the explanation must name the cause"
    assert retired.retirement_basis == "recorded_at"


def test_evidence_accumulates_under_one_fact(resolver):
    decision = resolver.explain(AUTH).decision
    assert decision.evidence_count == 2
    assert {e.artifact_type for e in decision.evidence} == {"adr", "pull_request"}


def test_support_reflects_confidence_and_authority(resolver):
    """Three ADRs should outweigh one commit message; support makes that visible."""
    decision = resolver.explain(AUTH).decision
    superseded = next(n for n in resolver.explain(AUTH).history if n.object_label == "JWT")
    assert decision.support > superseded.support


def test_asking_from_the_winning_side_shows_what_it_replaced(resolver):
    """"Why OAuth2" is only half answered without "instead of what"."""
    belief = resolver.explain("OAuth2")
    assert any(n.object_label == "JWT" for n in belief.history)


def test_unknown_entity_is_reported_not_invented(resolver):
    belief = resolver.explain("Kerberos")
    assert not belief.answered
    assert belief.diagnostics
    assert "Kerberos" in render(belief)


def test_bound_but_unused_entity_is_distinguished_from_unknown():
    """
    "I never heard of it" and "I know the name but it never became knowledge"
    are different answers and memory should not conflate them.
    """
    memory = InMemoryProjectMemory()
    Ingestor(memory=memory).ingest(
        make_artifact("This mentions Redis in passing.\n", ArtifactType.COMMIT, "2024-01-01")
    )
    belief = BeliefResolver(memory).explain("Redis")
    assert not belief.answered
    assert "never became knowledge" in " ".join(belief.diagnostics)


def test_resolution_never_mutates_memory():
    memory = InMemoryProjectMemory()
    ingestor = Ingestor(memory=memory)
    for content, atype, when in CORPUS:
        ingestor.ingest(make_artifact(content, atype, when))

    before = memory.stats()
    for query in (AUTH, "OAuth2", "JWT", "nonexistent"):
        BeliefResolver(memory).explain(query)
    assert memory.stats() == before


def test_render_contains_the_full_explanation(resolver):
    text = render(resolver.explain(AUTH))
    assert "CURRENT" in text
    assert "SUPERSEDED" in text
    assert "OAuth2" in text and "JWT" in text
    assert "support=" in text


def test_predicate_filter_narrows_the_answer(resolver):
    belief = resolver.explain(AUTH, predicates=(Predicate.SELECTED,))
    assert all(n.predicate is Predicate.SELECTED for n in belief.current)
