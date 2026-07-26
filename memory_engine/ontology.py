"""
Ontology

The fixed vocabulary the compiler normalizes free text into.

EntityType - what a thing IS (a component, a person, a decision, ...)
Predicate  - how two things RELATE (uses, depends_on, has_reason, ...)

Extractors map loosely-worded statements onto these enums so that facts
from different artifacts (a PR vs. an ADR vs. a Slack thread) end up
comparable instead of each having their own private vocabulary.
"""
from enum import Enum


class EntityType(Enum):
    # Software architecture
    COMPONENT = "component"
    MODULE = "module"
    PACKAGE = "package"
    SERVICE = "service"
    API = "api"
    DATABASE = "database"
    LIBRARY = "library"
    FRAMEWORK = "framework"
    CLASS = "class"
    FUNCTION = "function"
    FILE = "file"

    # Capabilities
    FEATURE = "feature"
    CAPABILITY = "capability"

    # Documentation
    ADR = "adr"
    PR = "pull_request"
    ISSUE = "issue"
    DOCUMENT = "document"

    # Human
    PERSON = "person"
    TEAM = "team"

    # Concepts
    DECISION = "decision"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"
    RISK = "risk"
    GOAL = "goal"

    UNKNOWN = "unknown"


class Predicate(Enum):
    # Structural relationships
    USES = "uses"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    CONTAINS = "contains"
    BELONGS_TO = "belongs_to"
    CALLS = "calls"
    EXPOSES = "exposes"
    IMPORTS = "imports"
    REFERENCES = "references"

    # Architectural decisions
    SELECTED = "selected"
    REJECTED = "rejected"
    REPLACED_BY = "replaced_by"
    DEPRECATED = "deprecated"
    INTRODUCES = "introduces"
    REMOVES = "removes"

    # Design rationale
    HAS_REASON = "has_reason"
    HAS_TRADEOFF = "has_tradeoff"
    HAS_BENEFIT = "has_benefit"
    HAS_RISK = "has_risk"
    HAS_ASSUMPTION = "has_assumption"

    # Constraints
    REQUIRES = "requires"
    PROHIBITS = "prohibits"
    ALLOWS = "allows"

    # Miscellaneous
    DESCRIBES = "describes"
    UNKNOWN = "unknown"
