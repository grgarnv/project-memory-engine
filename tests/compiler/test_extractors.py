"""Extractor units: entities, LLM abstraction, resolution, relations."""
import json

import pytest

from memory_engine.compiler.extractors import (
    CompositeEntityRecognizer,
    DeterministicEntityResolver,
    GeneralEntityRecognizer,
    PhraseEntityRecognizer,
    RuleBasedRelationExtractor,
)
from memory_engine.compiler.extractors.llm import (
    GeminiProvider,
    LLMStatementExtractor,
    MockLLMProvider,
    OpenAIProvider,
)
from memory_engine.ir import Claim, Entity, Fact, Segment, SegmentKind
from memory_engine.ontology import EntityType, Predicate


def test_general_recognizer_finds_software_vocabulary():
    entities = GeneralEntityRecognizer().recognize(
        "Deploying Redis and PostgreSQL on Kubernetes using React with OAuth and Kafka."
    )
    names = {e.canonical_name.lower() for e in entities}
    assert {"redis", "postgresql", "kubernetes", "react", "oauth", "kafka"} <= names


def test_phrase_recognizer_registers_relational_operands():
    entities = PhraseEntityRecognizer().recognize(
        "Use OAuth2 for service-to-service authentication."
    )
    names = {e.canonical_name.lower() for e in entities}
    assert "service-to-service authentication" in names
    assert "oauth2" in names


def test_composite_suppresses_subsumed_names():
    """"authentication" inside "service-to-service authentication" is noise."""
    recognizer = CompositeEntityRecognizer(
        [GeneralEntityRecognizer(), PhraseEntityRecognizer()]
    )
    names = {
        e.canonical_name.lower()
        for e in recognizer.recognize("Use OAuth2 for service-to-service authentication.")
    }
    assert "service-to-service authentication" in names
    assert "authentication" not in names


def test_capability_type_is_inferred_from_head_noun():
    entities = PhraseEntityRecognizer().recognize("Use Redis for session caching.")
    caching = next(e for e in entities if "caching" in e.canonical_name.lower())
    assert caching.entity_type is EntityType.CAPABILITY


def test_resolution_and_relation_construction():
    gateway = Entity(canonical_name="API Gateway", entity_type=EntityType.COMPONENT)
    jwt = Entity(canonical_name="JWT validation", entity_type=EntityType.FEATURE)
    claim = Claim(subject="API Gateway", predicate="uses",
                  target="JWT validation", confidence=0.85)
    fact = Fact(subject="API Gateway", predicate=Predicate.USES,
                object="JWT validation", source_claim=claim.id)

    resolved = DeterministicEntityResolver().resolve([fact], [gateway, jwt], [claim])
    assert resolved[0].subject_entity is gateway
    assert resolved[0].object_entity is jwt
    assert resolved[0].confidence == 0.85

    relations = RuleBasedRelationExtractor().extract(resolved)
    assert len(relations) == 1
    assert relations[0].source_fact_id == fact.id


def test_unresolved_operands_produce_no_relation():
    """The linker must never be handed a guess."""
    fact = Fact(subject="Something Unknown", predicate=Predicate.USES, object="Also Unknown")
    resolved = DeterministicEntityResolver().resolve([fact], [], [])
    assert RuleBasedRelationExtractor().extract(resolved) == []


def test_llm_extractor_parses_provider_json():
    provider = MockLLMProvider(canned_response=json.dumps(
        [{"subject": "Service A", "predicate": "uses", "target": "Service B"}]
    ))
    statements = LLMStatementExtractor(provider=provider).extract(
        Segment(kind=SegmentKind.DESCRIPTION, text="Service A uses Service B")
    )
    assert (statements[0].subject, statements[0].predicate, statements[0].target) == (
        "Service A", "uses", "Service B"
    )


def test_llm_extractor_degrades_instead_of_raising():
    statements = LLMStatementExtractor(
        provider=MockLLMProvider(canned_response="not json at all")
    ).extract(Segment(kind=SegmentKind.DESCRIPTION, text="Some text"))
    assert len(statements) == 1


def test_providers_require_credentials():
    with pytest.raises(ValueError, match="OpenAI API key missing"):
        OpenAIProvider(api_key="")
    with pytest.raises(ValueError, match="Gemini API key missing"):
        GeminiProvider(api_key="")
