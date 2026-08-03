"""
Identity resolution over same_as edges.

A merge is an assertion with evidence, not a mutation. Content-addressed IDs
cannot be rewritten, so equivalence is computed at read time.
"""
import pytest

from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.resolve import BeliefResolver, IdentityResolver
from memory_engine.resolve.identity import MAX_CLASS_SIZE
from memory_engine.store import InMemoryProjectMemory
from tests.conftest import make_artifact

ALIAS = "The API Gateway is also known as the edge service.\n"
USES = "## Decision\n\nThe API Gateway uses OAuth2.\n"
DEPENDS = "## Decision\n\nThe edge service depends on the token service.\n"


def _memory(*docs):
    memory = InMemoryProjectMemory()
    ingestor = Ingestor(memory=memory)
    for i, (content, atype) in enumerate(docs):
        ingestor.ingest(make_artifact(content, atype, f"2024-0{i + 1}-01"))
    return memory


def test_alias_is_extracted_as_a_fact():
    memory = _memory((ALIAS, ArtifactType.DOCUMENT))
    from memory_engine.ontology import Predicate
    assert any(f.predicate is Predicate.SAME_AS for f in memory.facts.values())


def test_asking_by_either_name_returns_the_whole_concept():
    memory = _memory((USES, ArtifactType.ADR), (ALIAS, ArtifactType.DOCUMENT),
                     (DEPENDS, ArtifactType.ADR))
    for name in ("API Gateway", "edge service"):
        objects = {n.object_label for n in BeliefResolver(memory).explain(name).current}
        assert "OAuth2" in objects
        assert "token service" in objects


def test_same_as_edges_are_not_themselves_an_answer():
    memory = _memory((USES, ArtifactType.ADR), (ALIAS, ArtifactType.DOCUMENT))
    from memory_engine.ontology import Predicate
    belief = BeliefResolver(memory).explain("API Gateway")
    assert all(n.predicate is not Predicate.SAME_AS for n in belief.current)


def test_canonical_label_is_deterministic():
    memory = _memory((USES, ArtifactType.ADR), (ALIAS, ArtifactType.DOCUMENT))
    resolver = IdentityResolver(memory)
    ref = memory.resolve_ref("API Gateway")
    first = resolver.equivalence_class(ref).canonical_label
    second = resolver.equivalence_class(memory.resolve_ref("edge service")).canonical_label
    assert first == second, "either name must produce the same canonical label"


def test_merged_identity_is_disclosed_in_the_answer():
    """An answer assembled across names must say so."""
    memory = _memory((USES, ArtifactType.ADR), (ALIAS, ArtifactType.DOCUMENT))
    belief = BeliefResolver(memory).explain("API Gateway")
    assert belief.identity.is_merged
    assert any("same concept" in d for d in belief.diagnostics)


def test_unmerged_entity_has_a_class_of_one():
    memory = _memory((USES, ArtifactType.ADR))
    klass = IdentityResolver(memory).equivalence_class(memory.resolve_ref("OAuth2"))
    assert not klass.is_merged
    assert klass.refs == [memory.resolve_ref("OAuth2")]


def test_cycles_do_not_hang():
    """A same_as B and B same_as A is normal in an append-only edge set."""
    memory = _memory(
        (ALIAS, ArtifactType.DOCUMENT),
        ("The edge service is also known as the API Gateway.\n", ArtifactType.DOCUMENT),
    )
    klass = IdentityResolver(memory).equivalence_class(memory.resolve_ref("API Gateway"))
    assert len(klass.refs) == 2


def test_traversal_is_bounded():
    assert MAX_CLASS_SIZE > 1


def test_retracted_merge_is_not_followed():
    """A superseded same_as is not a merge; history stays queryable."""
    memory = _memory((USES, ArtifactType.ADR), (ALIAS, ArtifactType.DOCUMENT))
    same_as = next(f for f in memory.facts.values()
                   if f.predicate.value == "same_as")
    memory.superseded_fact_ids.add(same_as.id)

    klass = IdentityResolver(memory).equivalence_class(memory.resolve_ref("API Gateway"))
    assert not klass.is_merged
