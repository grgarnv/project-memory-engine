"""Extractor interfaces and the promotion threshold."""
from __future__ import annotations

from abc import ABC, abstractmethod

from memory_engine.ir import Claim, Entity, Fact, Relation, Segment, Statement

# The artifact talking about itself. Resolved by the linker to an ArtifactRef,
# never to a domain entity.
CURRENT_CHANGE = "Current Change"

# A Claim is promoted to a Fact only at or above this confidence.
FACT_CONFIDENCE_THRESHOLD = 0.7


class StatementExtractor(ABC):
    @abstractmethod
    def extract(self, segment: Segment) -> list[Statement]:
        """Convert one Segment into zero or more Statements."""


class FactExtractor(ABC):
    @abstractmethod
    def extract(self, claim: Claim) -> list[Fact]:
        """Promote a Claim to a Fact, or return [] to leave it a Claim."""


class EntityRecognizer(ABC):
    @abstractmethod
    def recognize(self, text: str) -> list[Entity]:
        """Extract entity mentions from text."""


class EntityResolver(ABC):
    @abstractmethod
    def resolve(self, facts, entities, claims=None):
        """Resolve fact operands against extracted entities."""


class RelationExtractor(ABC):
    @abstractmethod
    def extract(self, resolved_facts) -> list[Relation]:
        """Build Entity--predicate-->Entity edges from resolved facts."""
