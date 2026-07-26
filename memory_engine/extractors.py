"""
Extractors

Pluggable logic for turning one IR object into another. Two interfaces:

    StatementExtractor.extract(segment)   -> list[Statement]
    FactExtractor.extract(statement)      -> list[Fact]

Swap in a smarter (e.g. LLM-backed) extractor later by implementing the
same interface - the pipeline doesn't care which one it's given.
"""
from abc import ABC, abstractmethod

from memory_engine.ir import Segment, SegmentKind, Statement, Claim, Fact, FactType
from memory_engine.ontology import Predicate

CURRENT_CHANGE = "Current Change"

# A Claim is promoted to a Fact only above this confidence. Named constant
# rather than a bare number so the cutoff is obvious and easy to tune
# without reading FactExtractor's implementation.
FACT_CONFIDENCE_THRESHOLD = 0.7


class StatementExtractor(ABC):
    @abstractmethod
    def extract(self, segment: Segment) -> list[Statement]:
        """Convert one Segment into zero or more Statements."""


class FactExtractor(ABC):
    @abstractmethod
    def extract(self, claim: Claim) -> list[Fact]:
        """Decide whether a Claim is concrete and structured enough to be
        promoted to a Fact. Returns [] if it should remain a Claim only."""


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
    """Filters Claims into Facts. A Claim is promoted only if both hold:

      - concrete enough:    confidence >= FACT_CONFIDENCE_THRESHOLD
      - structured enough:  predicate maps to a known ontology Predicate

    Otherwise the claim remains a Claim only - this method returns [].
    """

    def extract(self, claim: Claim) -> list[Fact]:
        predicate = _PREDICATE_MAP.get(claim.predicate, Predicate.UNKNOWN)

        if claim.confidence < FACT_CONFIDENCE_THRESHOLD:
            return []

        if predicate is Predicate.UNKNOWN:
            return []

        return [
            Fact(
                subject=claim.subject,
                predicate=predicate,
                object=claim.target,
                fact_type=FactType.OBSERVATION,
                source_claim=claim.id,
                supporting_statements=list(claim.supporting_statements),
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
