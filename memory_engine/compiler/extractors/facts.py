"""
Fact promotion.

A Claim becomes a Fact only if it is both:
  - confident enough:   confidence >= FACT_CONFIDENCE_THRESHOLD
  - structured enough:  its predicate maps onto a known ontology Predicate

Everything else stays a Claim. The compiler never invents a predicate it does
not have taxonomy for; unmapped predicates are dropped, not guessed.
"""
from __future__ import annotations

from memory_engine.compiler.extractors.base import (
    FACT_CONFIDENCE_THRESHOLD,
    FactExtractor,
)
from memory_engine.ir import Claim, Fact, FactType
from memory_engine.ontology import OntologyRegistry, Predicate, default_ontology_registry

# Which fact type a predicate produces. Presentation-level, not epistemic.
_DECISION_PREDICATES = {
    Predicate.SELECTED, Predicate.REJECTED,
    Predicate.REPLACED_BY, Predicate.DEPRECATED,
}
_CONSTRAINT_PREDICATES = {
    Predicate.REQUIRES, Predicate.PROHIBITS, Predicate.ALLOWS,
}
_RELATIONSHIP_PREDICATES = {
    Predicate.USES, Predicate.DEPENDS_ON, Predicate.CONTAINS,
    Predicate.IMPLEMENTS, Predicate.EXTENDS, Predicate.CALLS,
    Predicate.EXPOSES, Predicate.IMPORTS, Predicate.BELONGS_TO,
    Predicate.REMOVES, Predicate.INTRODUCES,
}


def _fact_type_for(predicate: Predicate) -> FactType:
    if predicate in _DECISION_PREDICATES:
        return FactType.DECISION
    if predicate in _CONSTRAINT_PREDICATES:
        return FactType.CONSTRAINT
    if predicate in _RELATIONSHIP_PREDICATES:
        return FactType.RELATIONSHIP
    return FactType.OBSERVATION


class RuleBasedFactExtractor(FactExtractor):
    def __init__(self, registry: OntologyRegistry | None = None):
        self.registry = registry or default_ontology_registry()

    def extract(self, claim: Claim) -> list[Fact]:
        predicate = self.registry.normalize_predicate(claim.predicate)

        if claim.confidence < FACT_CONFIDENCE_THRESHOLD:
            return []
        if predicate is Predicate.UNKNOWN:
            return []

        return [
            Fact(
                subject=claim.subject,
                predicate=predicate,
                object=claim.target,
                fact_type=_fact_type_for(predicate),
                source_claim=claim.id,
                confidence=claim.confidence,
                supporting_statements=list(claim.supporting_statements),
            )
        ]
