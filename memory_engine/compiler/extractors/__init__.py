"""Pluggable extraction logic. Swap any piece by implementing its interface."""
from memory_engine.compiler.extractors.base import (
    CURRENT_CHANGE,
    FACT_CONFIDENCE_THRESHOLD,
    EntityRecognizer,
    EntityResolver,
    FactExtractor,
    RelationExtractor,
    StatementExtractor,
)
from memory_engine.compiler.extractors.entities import (
    CompositeEntityRecognizer,
    GeneralEntityRecognizer,
    PhraseEntityRecognizer,
    default_entity_recognizer,
)
from memory_engine.compiler.extractors.facts import RuleBasedFactExtractor
from memory_engine.compiler.extractors.relations import (
    DeterministicEntityResolver,
    ResolvedFact,
    RuleBasedRelationExtractor,
)
from memory_engine.compiler.extractors.statements import (
    CompositeStatementExtractor,
    RelationalStatementExtractor,
    RuleBasedStatementExtractor,
    default_statement_extractor,
)

__all__ = [
    "CURRENT_CHANGE",
    "FACT_CONFIDENCE_THRESHOLD",
    "StatementExtractor",
    "FactExtractor",
    "EntityRecognizer",
    "EntityResolver",
    "RelationExtractor",
    "RuleBasedStatementExtractor",
    "RelationalStatementExtractor",
    "CompositeStatementExtractor",
    "default_statement_extractor",
    "RuleBasedFactExtractor",
    "GeneralEntityRecognizer",
    "PhraseEntityRecognizer",
    "CompositeEntityRecognizer",
    "default_entity_recognizer",
    "DeterministicEntityResolver",
    "RuleBasedRelationExtractor",
    "ResolvedFact",
]
