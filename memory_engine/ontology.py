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

    # Identity
    SAME_AS = "same_as"

    # Miscellaneous
    DESCRIBES = "describes"
    UNKNOWN = "unknown"


class OntologyVersion(Enum):
    V1_0 = "1.0"


class OntologyRegistry:
    """
    Centralized registry for ontology versioning, entity types, predicates, and mapping rules.

    The compiler consumes the ontology from this registry rather than hardcoding taxonomy rules inside extractor passes.
    """

    def __init__(
        self,
        version: OntologyVersion = OntologyVersion.V1_0,
        predicate_map: dict[str, Predicate] | None = None,
        segment_predicate_map: dict[str, str] | None = None,
    ):
        self.version = version
        self._predicate_map = predicate_map or {
            "description": Predicate.DESCRIBES,
            "has_reason": Predicate.HAS_REASON,
            "has_tradeoff": Predicate.HAS_TRADEOFF,
            "has_benefit": Predicate.HAS_BENEFIT,
            "has_risk": Predicate.HAS_RISK,
            "selected": Predicate.SELECTED,
            "rejected": Predicate.REJECTED,
            "describes": Predicate.DESCRIBES,
            "uses": Predicate.USES,
            "depends_on": Predicate.DEPENDS_ON,
            "requires": Predicate.REQUIRES,
            "prohibits": Predicate.PROHIBITS,
            "allows": Predicate.ALLOWS,
            "replaced_by": Predicate.REPLACED_BY,
            "deprecated": Predicate.DEPRECATED,
            "contains": Predicate.CONTAINS,
            "removes": Predicate.REMOVES,
            "introduces": Predicate.INTRODUCES,
            "implements": Predicate.IMPLEMENTS,
            "exposes": Predicate.EXPOSES,
            "same_as": Predicate.SAME_AS,
            "calls": Predicate.CALLS,
            "extends": Predicate.EXTENDS,
            "imports": Predicate.IMPORTS,
        }
        self._segment_predicate_map = segment_predicate_map or {
            "description": "description",
            "reason": "has_reason",
            "tradeoff": "has_tradeoff",
            "decision": "selected",
            "context": "has_reason",
            "status": "describes",
            "consequence": "has_tradeoff",
        }

    def normalize_predicate(self, raw_predicate: str) -> Predicate:
        """Map raw free-text predicate to formal ontology Predicate enum."""
        return self._predicate_map.get(raw_predicate.lower(), Predicate.UNKNOWN)

    def segment_kind_to_predicate(self, segment_kind_str: str) -> str:
        """Map SegmentKind string representation to raw statement predicate."""
        return self._segment_predicate_map.get(segment_kind_str.lower(), "unknown")

    def register_predicate_mapping(self, raw_predicate: str, ontology_predicate: Predicate) -> None:
        """Allow extending predicate mapping rules dynamically."""
        self._predicate_map[raw_predicate.lower()] = ontology_predicate


_DEFAULT_REGISTRY = OntologyRegistry()


def default_ontology_registry() -> OntologyRegistry:
    """Return default global ontology registry instance."""
    return _DEFAULT_REGISTRY

