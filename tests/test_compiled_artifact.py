from memory_engine.ir import (
    Artifact,
    ArtifactType,
    Observation,
    Segment,
    Statement,
    Claim,
    Fact,
    CompiledArtifact,
    deterministic_id,
)
from memory_engine.ontology import Predicate, OntologyVersion
from memory_engine.pipeline import MemoryCompiler


def test_deterministic_id_generation():
    id1 = deterministic_id("artifact", "pr", "content_body_123")
    id2 = deterministic_id("artifact", "pr", "content_body_123")
    id3 = deterministic_id("artifact", "pr", "different_content")

    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("artifact_")


def test_compiled_artifact_dictionary_compatibility():
    artifact = Artifact(type=ArtifactType.PR, content="# Title\n\nBody text.")
    compiled = MemoryCompiler().compile(artifact)

    assert isinstance(compiled, CompiledArtifact)
    # Dictionary indexing compatibility
    assert "statements" in compiled
    assert "facts" in compiled
    assert isinstance(compiled["statements"], list)
    assert isinstance(compiled["facts"], list)
    assert compiled.fact_count == len(compiled.facts)


def test_compiled_artifact_serialization():
    artifact = Artifact(type=ArtifactType.PR, content="Reason: Test performance")
    compiled = MemoryCompiler().compile(artifact)

    d = compiled.to_dict()
    assert "artifact_id" in d
    assert "observations" in d
    assert "ontology_version" in d
    assert d["ontology_version"] == OntologyVersion.V1_0.value

    json_str = compiled.to_json()
    assert '"ontology_version": "1.0"' in json_str


def test_section_header_hierarchical_preservation():
    doc = "# Architecture Decision\n\n## Context\nContext explanation.\n\n## Decision\nWe selected OAuth2."
    artifact = Artifact(type=ArtifactType.ADR, content=doc)
    compiled = MemoryCompiler().compile(artifact)

    obs_headers = [o.section_header for o in compiled.observations if o.section_header]
    seg_headers = [s.section_header for s in compiled.segments if s.section_header]

    assert "Context" in obs_headers or "Decision" in obs_headers
    assert "Context" in seg_headers or "Decision" in seg_headers
