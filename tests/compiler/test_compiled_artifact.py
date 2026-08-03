"""The compiler output contract."""
from memory_engine.ontology import OntologyVersion
from tests.conftest import make_artifact

CONTENT = "Migrate the API Gateway to OAuth2.\n\nReason:\n\nToken revocation.\n"


def test_typed_access_and_dict_access_agree(compiler):
    result = compiler.compile(make_artifact(CONTENT))
    assert result["facts"] is result.facts
    assert result["entities"] is result.entities
    assert "facts" in result


def test_versions_are_recorded(compiler):
    """
    Reproducibility is conditional on compiler and ontology version, so a
    compilation that does not record them cannot be re-derived later.
    """
    result = compiler.compile(make_artifact(CONTENT))
    assert result.ontology_version is OntologyVersion.V1_0
    assert result.compiler_version


def test_json_round_trip(compiler):
    import json
    result = compiler.compile(make_artifact(CONTENT))
    payload = json.loads(result.to_json())
    assert payload["artifact_id"] == result.artifact.id
    assert len(payload["facts"]) == result.fact_count


def test_lookup_helpers(compiler):
    result = compiler.compile(make_artifact(CONTENT))
    entity = result.entities[0]
    assert result.entity_by_id(entity.id) is entity
    assert result.entity_by_id("nope") is None
