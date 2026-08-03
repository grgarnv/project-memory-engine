"""
The read path: resolving accumulated evidence into current belief.

Core infrastructure, not an application. Explanation engines, compliance
engines, and onboarding assistants are built on this - they are not it.
"""
from memory_engine.resolve.explain import explain, phrase
from memory_engine.resolve.queries import (
    Dependent,
    HealthReport,
    ProjectQueries,
    TimelineEntry,
)
from memory_engine.resolve.identity import EquivalenceClass, IdentityResolver
from memory_engine.resolve.render import render
from memory_engine.resolve.resolver import (
    DECISION_PREDICATES,
    BeliefNode,
    BeliefResolver,
    EvidenceView,
    ResolvedBelief,
)

__all__ = [
    "BeliefResolver",
    "ResolvedBelief",
    "BeliefNode",
    "EvidenceView",
    "DECISION_PREDICATES",
    "IdentityResolver",
    "EquivalenceClass",
    "render",
    "explain",
    "phrase",
    "ProjectQueries",
    "TimelineEntry",
    "Dependent",
    "HealthReport",
]
