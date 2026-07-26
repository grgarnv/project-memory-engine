import pytest
from memory_engine.ontology import (
    Predicate,
    EntityType,
    OntologyVersion,
    OntologyRegistry,
    default_ontology_registry,
)


def test_ontology_version_default():
    registry = OntologyRegistry()
    assert registry.version == OntologyVersion.V1_0


def test_normalize_predicate_known_and_unknown():
    registry = OntologyRegistry()
    assert registry.normalize_predicate("description") == Predicate.DESCRIBES
    assert registry.normalize_predicate("has_reason") == Predicate.HAS_REASON
    assert registry.normalize_predicate("selected") == Predicate.SELECTED
    assert registry.normalize_predicate("unknown_custom_pred") == Predicate.UNKNOWN


def test_segment_kind_mapping():
    registry = OntologyRegistry()
    assert registry.segment_kind_to_predicate("reason") == "has_reason"
    assert registry.segment_kind_to_predicate("tradeoff") == "has_tradeoff"
    assert registry.segment_kind_to_predicate("decision") == "selected"


def test_custom_predicate_registration():
    registry = OntologyRegistry()
    registry.register_predicate_mapping("custom_uses", Predicate.USES)
    assert registry.normalize_predicate("custom_uses") == Predicate.USES


def test_default_registry_singleton():
    reg1 = default_ontology_registry()
    reg2 = default_ontology_registry()
    assert reg1 is reg2
