from pathlib import Path

from memory_engine.ir import Artifact, ArtifactType
from memory_engine.ontology import EntityType, Predicate
from memory_engine.pipeline import MemoryCompiler

SAMPLE = Path(__file__).parent / "golden" / "pr_001" / "input.md"


def test_entities_are_extracted():
    artifact = Artifact(type=ArtifactType.PR, content=SAMPLE.read_text())
    result = MemoryCompiler().compile(artifact)

    names = {e.canonical_name.lower() for e in result["entities"]}
    assert "api gateway" in names
    assert any(e.entity_type == EntityType.COMPONENT for e in result["entities"])


def test_facts_are_normalized_against_ontology():
    artifact = Artifact(type=ArtifactType.PR, content=SAMPLE.read_text())
    result = MemoryCompiler().compile(artifact)

    predicates = {f.predicate for f in result["facts"]}
    assert predicates == {Predicate.DESCRIBES, Predicate.HAS_REASON, Predicate.HAS_TRADEOFF}


def test_claims_carry_confidence():
    artifact = Artifact(type=ArtifactType.PR, content=SAMPLE.read_text())
    result = MemoryCompiler().compile(artifact)

    assert len(result["claims"]) == len(result["statements"])
    assert all(0.0 <= c.confidence <= 1.0 for c in result["claims"])


def test_confident_claim_is_promoted_to_fact():
    artifact = Artifact(type=ArtifactType.PR, content=SAMPLE.read_text())
    result = MemoryCompiler().compile(artifact)

    assert len(result["claims"]) == len(result["facts"])
    for fact in result["facts"]:
        assert fact.source_claim  # provenance link back to the Claim is set


def test_hedged_claim_is_not_promoted_to_fact():
    hedged = "# Pull Request\n\nThis should improve performance.\n"
    artifact = Artifact(type=ArtifactType.PR, content=hedged)
    result = MemoryCompiler().compile(artifact)

    assert len(result["claims"]) == 1
    assert result["claims"][0].confidence < 0.7
    assert len(result["facts"]) == 0
