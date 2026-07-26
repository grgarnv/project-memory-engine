"""
Memory IR (Intermediate Representation)

Every object the compiler passes between stages lives here, in one file,
so the whole data model can be read top to bottom without file-hunting.

Pipeline shape:

    Artifact -> Observation -> Segment -> Statement -> Fact / Claim -> MemoryPatch
                                              |
                                              +-> Entity

Artifact    raw input (a PR, commit, ADR, ...)
Observation artifact chunked into typed paragraphs
Segment     an observation split by semantic role (description/reason/tradeoff)
Statement   a segment turned into a (subject, predicate, target) triple
Entity      a named thing (component, feature, ...) pulled out of a segment
Fact        a statement normalized against the ontology's Predicate enum
Claim       a statement wrapped with a confidence score (future: merged
            across multiple statements once we have more than one source)
MemoryPatch the diff to apply to long-term project memory (not wired up yet
            - see docs/roadmap.md)
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import uuid

from memory_engine.ontology import Predicate


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class ArtifactType(Enum):
    PR = "pull_request"
    COMMIT = "commit"
    ADR = "adr"
    ISSUE = "issue"
    SLACK = "slack"
    DOCUMENT = "document"
    CODE = "code"


@dataclass(slots=True)
class Artifact:
    id: str = field(default_factory=_uid)
    type: ArtifactType = ArtifactType.DOCUMENT
    source: Path | None = None
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 1: Observation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Observation:
    id: str = field(default_factory=_uid)
    text: str = ""
    type: str = "paragraph"  # header | paragraph | reason | tradeoff
    confidence: float = 1.0
    artifact_id: str = ""


# ---------------------------------------------------------------------------
# Stage 2: Segment
# ---------------------------------------------------------------------------

class SegmentKind(Enum):
    DESCRIPTION = "description"
    REASON = "reason"
    TRADEOFF = "tradeoff"


@dataclass(slots=True)
class Segment:
    id: str = field(default_factory=_uid)
    kind: SegmentKind = SegmentKind.DESCRIPTION
    text: str = ""
    observation_id: str = ""


# ---------------------------------------------------------------------------
# Stage 3: Statement
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Statement:
    id: str = field(default_factory=_uid)
    subject: str = ""
    predicate: str = ""
    target: str = ""
    confidence: float = 1.0
    observation_id: str = ""


# ---------------------------------------------------------------------------
# Stage 4: Entity (extracted alongside statements, from the same segments)
# ---------------------------------------------------------------------------

from memory_engine.ontology import EntityType  # noqa: E402  (avoid circular import at top)


@dataclass(slots=True)
class Entity:
    id: str = field(default_factory=_uid)
    canonical_name: str = ""
    entity_type: EntityType = EntityType.UNKNOWN
    aliases: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 5a: Fact - statement normalized against the ontology
# ---------------------------------------------------------------------------

class FactType(Enum):
    RELATIONSHIP = "relationship"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    OBSERVATION = "observation"


@dataclass(slots=True)
class Fact:
    id: str = field(default_factory=_uid)
    subject: str = ""
    predicate: Predicate = Predicate.UNKNOWN
    object: str = ""
    fact_type: FactType = FactType.OBSERVATION
    supporting_statements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5b: Claim - statement wrapped with a confidence score
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Claim:
    id: str = field(default_factory=_uid)
    subject: str = ""
    predicate: str = ""
    target: str = ""
    confidence: float = 0.5
    supporting_statements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 6: MemoryPatch (future - not produced by the pipeline yet)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class MemoryPatch:
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
