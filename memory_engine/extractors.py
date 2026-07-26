"""
Extractors

Pluggable logic for turning one IR object into another. Two interfaces:

    StatementExtractor.extract(segment)   -> list[Statement]
    FactExtractor.extract(statement)      -> list[Fact]

Swap in a smarter (e.g. LLM-backed) extractor later by implementing the
same interface - the pipeline doesn't care which one it's given.
"""
from abc import ABC, abstractmethod

from memory_engine.ir import Segment, SegmentKind, Statement, Fact, FactType
from memory_engine.ontology import Predicate

CURRENT_CHANGE = "Current Change"


class StatementExtractor(ABC):
    @abstractmethod
    def extract(self, segment: Segment) -> list[Statement]:
        """Convert one Segment into zero or more Statements."""


class FactExtractor(ABC):
    @abstractmethod
    def extract(self, statement: Statement) -> list[Fact]:
        """Convert one Statement into zero or more Facts."""


# Segment kind -> free-text predicate used by the statement layer.
_SEGMENT_PREDICATES = {
    SegmentKind.DESCRIPTION: "description",
    SegmentKind.REASON: "has_reason",
    SegmentKind.TRADEOFF: "has_tradeoff",
}

# Free-text predicate -> ontology Predicate used by the fact layer.
_PREDICATE_MAP = {
    "description": Predicate.DESCRIBES,
    "has_reason": Predicate.HAS_REASON,
    "has_tradeoff": Predicate.HAS_TRADEOFF,
}


class RuleBasedStatementExtractor(StatementExtractor):
    """Deterministic segment-kind -> predicate mapping. No ML involved."""

    def extract(self, segment: Segment) -> list[Statement]:
        predicate = _SEGMENT_PREDICATES.get(segment.kind, "unknown")
        return [
            Statement(
                subject=CURRENT_CHANGE,
                predicate=predicate,
                target=segment.text,
                observation_id=segment.observation_id,
            )
        ]


class RuleBasedFactExtractor(FactExtractor):
    """Normalizes a Statement's free-text predicate into the ontology."""

    def extract(self, statement: Statement) -> list[Fact]:
        return [
            Fact(
                subject=statement.subject,
                predicate=_PREDICATE_MAP.get(statement.predicate, Predicate.UNKNOWN),
                object=statement.target,
                fact_type=FactType.OBSERVATION,
                supporting_statements=[statement.id],
            )
        ]


class LLMStatementExtractor(StatementExtractor):
    """
    Placeholder for an LLM-backed extractor.

    Not implemented yet - this is a Phase 1 item (see docs/roadmap.md).
    Kept here, rather than as a silent empty file, so the intended
    interface is visible and the gap is explicit instead of implicit.
    """

    def extract(self, segment: Segment) -> list[Statement]:
        raise NotImplementedError(
            "LLMStatementExtractor is planned for Phase 1 - see docs/roadmap.md"
        )
