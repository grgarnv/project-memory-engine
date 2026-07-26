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


def test_general_entity_recognizer_software_concepts():
    from memory_engine.extractors import GeneralEntityRecognizer
    recognizer = GeneralEntityRecognizer()
    text = "Deploying Redis and PostgreSQL on Kubernetes using React frontend with OAuth and Kafka messaging."
    entities = recognizer.recognize(text)
    names = {e.canonical_name.lower() for e in entities}

    assert "redis" in names
    assert "postgresql" in names
    assert "kubernetes" in names
    assert "react" in names
    assert "oauth" in names
    assert "kafka" in names


def test_llm_statement_extractor_with_mock_provider():
    import json
    from memory_engine.ir import Segment, SegmentKind
    from memory_engine.extractors import LLMStatementExtractor, MockLLMProvider

    canned = json.dumps([
        {"subject": "Service A", "predicate": "uses", "target": "Service B"}
    ])
    provider = MockLLMProvider(canned_response=canned)
    extractor = LLMStatementExtractor(provider=provider)

    segment = Segment(kind=SegmentKind.DESCRIPTION, text="Service A uses Service B")
    statements = extractor.extract(segment)

    assert len(statements) == 1
    assert statements[0].subject == "Service A"
    assert statements[0].predicate == "uses"
    assert statements[0].target == "Service B"


def test_llm_provider_raises_missing_api_key():
    import pytest
    from memory_engine.extractors import OpenAIProvider, GeminiProvider

    with pytest.raises(ValueError, match="OpenAI API key missing"):
        OpenAIProvider(api_key="")

    with pytest.raises(ValueError, match="Gemini API key missing"):
        GeminiProvider(api_key="")


def test_entity_resolution_and_relation_extraction():
    from memory_engine.ir import Fact, Entity, Claim
    from memory_engine.ontology import EntityType, Predicate
    from memory_engine.extractors import DeterministicEntityResolver, RuleBasedRelationExtractor

    ent_a = Entity(canonical_name="API Gateway", entity_type=EntityType.COMPONENT)
    ent_b = Entity(canonical_name="JWT validation", entity_type=EntityType.FEATURE)
    entities = [ent_a, ent_b]

    claim = Claim(subject="API Gateway", predicate="uses", target="JWT validation", confidence=0.85)
    fact = Fact(subject="API Gateway", predicate=Predicate.USES, object="JWT validation", source_claim=claim.id)

    resolver = DeterministicEntityResolver()
    resolved_facts = resolver.resolve([fact], entities, [claim])

    assert len(resolved_facts) == 1
    assert resolved_facts[0].subject_entity == ent_a
    assert resolved_facts[0].object_entity == ent_b
    assert resolved_facts[0].confidence == 0.85

    extractor = RuleBasedRelationExtractor()
    relations = extractor.extract(resolved_facts)

    assert len(relations) == 1
    assert relations[0].subject_entity_id == ent_a.id
    assert relations[0].object_entity_id == ent_b.id
    assert relations[0].predicate == Predicate.USES
    assert relations[0].source_fact_id == fact.id
    assert relations[0].confidence == 0.85


def test_unresolved_entities_do_not_produce_relations():
    from memory_engine.ir import Fact, Entity
    from memory_engine.ontology import EntityType, Predicate
    from memory_engine.extractors import DeterministicEntityResolver, RuleBasedRelationExtractor

    ent_a = Entity(canonical_name="API Gateway", entity_type=EntityType.COMPONENT)
    entities = [ent_a]

    # Subject is known, but object "Unknown Service" is not in entities list
    fact = Fact(subject="API Gateway", predicate=Predicate.USES, object="Unknown Service")

    resolver = DeterministicEntityResolver()
    resolved_facts = resolver.resolve([fact], entities)

    assert len(resolved_facts) == 1
    assert resolved_facts[0].subject_entity == ent_a
    assert resolved_facts[0].object_entity is None

    extractor = RuleBasedRelationExtractor()
    relations = extractor.extract(resolved_facts)

    # Cannot construct a valid Relation edge when object entity is unresolved
    assert len(relations) == 0


def test_ambiguous_entities_remain_unresolved():
    from memory_engine.ir import Fact, Entity
    from memory_engine.ontology import EntityType, Predicate
    from memory_engine.extractors import DeterministicEntityResolver

    # Two distinct entities sharing the exact same alias "Auth"
    ent1 = Entity(canonical_name="AuthComponent", entity_type=EntityType.COMPONENT, aliases=["Auth"])
    ent2 = Entity(canonical_name="AuthService", entity_type=EntityType.SERVICE, aliases=["Auth"])
    entities = [ent1, ent2]

    fact = Fact(subject="Auth", predicate=Predicate.USES, object="AuthComponent")

    resolver = DeterministicEntityResolver()
    resolved_facts = resolver.resolve([fact], entities)

    # Subject "Auth" is ambiguous (matches both ent1 and ent2) -> subject_entity MUST be None
    assert resolved_facts[0].subject_entity is None
    # Object "AuthComponent" is unique -> object_entity resolves to ent1
    assert resolved_facts[0].object_entity == ent1



