"""Ontology registry behaviour."""
from memory_engine.ontology import (
    EntityType,
    OntologyRegistry,
    OntologyVersion,
    Predicate,
    default_ontology_registry,
)


def test_registry_normalizes_known_predicates():
    registry = OntologyRegistry()
    assert registry.normalize_predicate("selected") is Predicate.SELECTED
    assert registry.normalize_predicate("replaced_by") is Predicate.REPLACED_BY


def test_unknown_predicate_is_not_invented():
    """RFC 003 non-goal 7: never infer missing taxonomy."""
    assert OntologyRegistry().normalize_predicate("frobnicates") is Predicate.UNKNOWN


def test_segment_kinds_map_to_predicates():
    registry = OntologyRegistry()
    assert registry.segment_kind_to_predicate("decision") == "selected"
    assert registry.segment_kind_to_predicate("reason") == "has_reason"


def test_mappings_are_extensible():
    registry = OntologyRegistry()
    registry.register_predicate_mapping("supersedes", Predicate.REPLACED_BY)
    assert registry.normalize_predicate("supersedes") is Predicate.REPLACED_BY


def test_version_is_pinned():
    assert default_ontology_registry().version is OntologyVersion.V1_0


def test_entity_types_cover_the_documented_taxonomy():
    for name in ("COMPONENT", "SERVICE", "DECISION", "CAPABILITY", "UNKNOWN"):
        assert hasattr(EntityType, name)
