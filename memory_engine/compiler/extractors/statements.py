"""
Statement extraction.

Two extractors run by default, composed:

    RuleBasedStatementExtractor   segment kind -> artifact-level assertion.
                                  "this ADR's decision section says <text>".
                                  Subject is always the artifact.

    RelationalStatementExtractor  surface patterns -> domain assertion.
                                  "service-to-service authentication selected OAuth2".
                                  Subject and object are project concepts.

Both are needed and they are not redundant. The first preserves what a document
said; the second is what makes the knowledge graph a graph. A system with only
the first can answer "what does ADR 012 say" - which is document retrieval. A
system with only the second loses the document's own voice.
"""
from __future__ import annotations

import re

from memory_engine.compiler.extractors.base import CURRENT_CHANGE, StatementExtractor
from memory_engine.compiler.extractors.patterns import find_relational_matches
from memory_engine.ir import Segment, Statement
from memory_engine.ontology import OntologyRegistry, default_ontology_registry


class RuleBasedStatementExtractor(StatementExtractor):
    """Deterministic segment-kind -> predicate mapping. Artifact-anchored."""

    def __init__(self, registry: OntologyRegistry | None = None):
        self.registry = registry or default_ontology_registry()

    def extract(self, segment: Segment) -> list[Statement]:
        predicate = self.registry.segment_kind_to_predicate(segment.kind.value)
        return [
            Statement(
                subject=CURRENT_CHANGE,
                predicate=predicate,
                target=segment.text,
                observation_id=segment.observation_id,
            )
        ]


class RelationalStatementExtractor(StatementExtractor):
    """
    Entity-anchored extraction from surface patterns.

    This is the extractor whose absence made every persisted fact point at the
    artifact that produced it. See docs/findings/read-path.md finding 1.
    """

    def extract(self, segment: Segment) -> list[Statement]:
        return [
            Statement(
                subject=match.subject,
                predicate=match.predicate,
                target=match.object,
                observation_id=segment.observation_id,
            )
            for match in find_relational_matches(segment.text)
        ]


class CompositeStatementExtractor(StatementExtractor):
    """Runs several extractors in order and concatenates their output."""

    def __init__(self, extractors: list[StatementExtractor]):
        self.extractors = extractors

    def extract(self, segment: Segment) -> list[Statement]:
        statements: list[Statement] = []
        for extractor in self.extractors:
            statements.extend(extractor.extract(segment))
        return statements


def default_statement_extractor(
    registry: OntologyRegistry | None = None,
) -> StatementExtractor:
    return CompositeStatementExtractor(
        [
            RuleBasedStatementExtractor(registry=registry),
            RelationalStatementExtractor(),
        ]
    )
