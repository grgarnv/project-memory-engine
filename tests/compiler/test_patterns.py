"""
Relational extraction - the fix for artifact-anchored facts.

Every persisted fact used to point at the artifact that produced it, so no
question about a concept could be answered. These tests pin the shape that
fixed it: (entity, predicate, entity).
"""
import pytest

from memory_engine.compiler.extractors.patterns import (
    find_relational_matches,
    is_usable_phrase,
    normalize_phrase,
)
from memory_engine.ontology import Predicate
from tests.conftest import make_artifact


@pytest.mark.parametrize("text,subject,predicate,obj", [
    ("Use OAuth2 for service-to-service authentication.",
     "service-to-service authentication", "selected", "OAuth2"),
    ("Replace JWT with OAuth2.", "JWT", "replaced_by", "OAuth2"),
    ("Migrate the API Gateway to OAuth2.", "API Gateway", "uses", "OAuth2"),
    ("Move JWT validation into the API Gateway.",
     "API Gateway", "contains", "JWT validation"),
    ("Remove JWT signing keys from the config service.",
     "config service", "removes", "JWT signing keys"),
    ("The billing service depends on Redis.", "billing service", "depends_on", "Redis"),
])
def test_pattern_yields_entity_anchored_triple(text, subject, predicate, obj):
    matches = find_relational_matches(text)
    triples = [(m.subject, m.predicate, m.object) for m in matches]
    assert (subject, predicate, obj) in triples


def test_decision_subject_is_the_capability_not_the_technology():
    """
    "Use X for Y" is a decision ABOUT Y. Getting this backwards would put every
    decision under a different subject and single-occupancy supersession could
    never fire.
    """
    match = find_relational_matches("Use OAuth2 for session storage.")[0]
    assert match.subject == "session storage"
    assert match.object == "OAuth2"


def test_phrase_normalization_trims_trailing_clauses():
    assert normalize_phrase(
        "service-to-service authentication across all internal services"
    ) == "service-to-service authentication"
    assert normalize_phrase("the API Gateway") == "API Gateway"


def test_whole_sentences_are_not_concepts():
    assert not is_usable_phrase(
        "a very long phrase that clearly is an entire clause and not a concept"
    )
    assert not is_usable_phrase("it")
    assert is_usable_phrase("API Gateway")


def test_compiled_facts_name_entities_not_the_artifact(compiler):
    """The regression guard for finding 1."""
    result = compiler.compile(
        make_artifact("## Decision\n\nUse OAuth2 for service-to-service authentication.\n")
    )
    decisions = [f for f in result["facts"] if f.predicate is Predicate.SELECTED]
    assert decisions, "a decision sentence must produce a SELECTED fact"
    assert any(f.subject.lower() != "current change" for f in decisions)


def test_fact_operands_also_exist_as_entities(compiler):
    """
    If a phrase can be a fact operand it must also be an entity, or the linker
    binds the fact to a raw string and the concept never enters the graph.
    """
    result = compiler.compile(
        make_artifact("Use OAuth2 for service-to-service authentication.\n")
    )
    names = {e.canonical_name.lower() for e in result["entities"]}
    for fact in result["facts"]:
        if fact.subject.lower() == "current change":
            continue
        assert fact.subject.lower() in names
        assert fact.object.lower() in names


def test_relations_are_built_for_resolved_facts(compiler):
    result = compiler.compile(
        make_artifact("Use OAuth2 for service-to-service authentication.\n")
    )
    assert result.relation_count >= 1
