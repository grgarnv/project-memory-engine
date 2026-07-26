"""
Memory IR (Intermediate Representation)

Every object the compiler passes between stages lives here, in one file,
so the whole data model can be read top to bottom without file-hunting.

Pipeline shape:

    Artifact -> Observation -> Segment -> Statement -> Claim -> Fact
                                              |
                                              +-> Entity

    MemoryPatch sits downstream of all of it - not produced yet.

Artifact    raw input (a PR, commit, ADR, ...)
Observation artifact chunked into typed paragraphs
Segment     an observation split by semantic role (description/reason/tradeoff)
Statement   a segment turned into a (subject, predicate, target) triple
Entity      a named thing (component, feature, ...) pulled out of a segment
Claim       something the artifact asserts - every Statement becomes a
            Claim, scored with a confidence heuristic. May be wrong,
            vague, or unstructured; that's fine, it's just a claim.
Fact        a Claim FactPass has accepted as structured knowledge - only
            promoted if it's both confident and maps onto a known
            ontology Predicate. Everything else stays a Claim only.
MemoryPatch the diff to apply to long-term project memory (not wired up yet
            - see docs/roadmap.md)
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import uuid

from memory_engine.ontology import Predicate


import hashlib
import json
from typing import Iterator

from memory_engine.ontology import Predicate, OntologyVersion


def _uid() -> str:
    return str(uuid.uuid4())


def deterministic_id(scope: str, *components: str) -> str:
    """
    Generate a stable, deterministic content-addressed hash ID.

    Usage:
        deterministic_id("artifact", artifact.type.value, artifact.content)
        deterministic_id("entity", entity_type.value, canonical_name.lower())
    """
    payload = f"{scope}:" + ":".join(str(c) for c in components)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{scope}_{digest}"


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
    section_header: str = ""
    parent_id: str = ""


# ---------------------------------------------------------------------------
# Stage 2: Segment
# ---------------------------------------------------------------------------

class SegmentKind(Enum):
    DESCRIPTION = "description"
    REASON = "reason"
    TRADEOFF = "tradeoff"
    DECISION = "decision"
    CONTEXT = "context"
    STATUS = "status"
    CONSEQUENCE = "consequence"


@dataclass(slots=True)
class Segment:
    id: str = field(default_factory=_uid)
    kind: SegmentKind = SegmentKind.DESCRIPTION
    text: str = ""
    observation_id: str = ""
    section_header: str = ""
    parent_id: str = ""


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
# Stage 5a: Claim - statement wrapped with a confidence score
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Claim:
    id: str = field(default_factory=_uid)
    subject: str = ""
    predicate: str = ""
    target: str = ""
    confidence: float = 1.0
    supporting_statements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5b: Fact - a Claim the compiler has accepted as structured knowledge
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
    source_claim: str = ""
    supporting_statements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5c: Relation - Entity-to-Entity edge produced from resolved Facts
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Relation:
    id: str = field(default_factory=_uid)
    subject_entity_id: str = ""
    predicate: Predicate = Predicate.UNKNOWN
    object_entity_id: str = ""
    source_fact_id: str = ""
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Compiler Output Contract: CompiledArtifact
# ---------------------------------------------------------------------------

@dataclass
class CompiledArtifact:
    """
    Immutable typed container for full compiler output.

    Provides dictionary compatibility (`__getitem__`, `to_dict()`) to preserve
    backwards compatibility with existing test suites while introducing typed
    inspection and metadata for MemoryPatch downstream.
    """
    artifact: Artifact
    observations: list[Observation] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    ontology_version: OntologyVersion = OntologyVersion.V1_0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(f"CompiledArtifact has no attribute or key '{item}'")

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def keys(self) -> list[str]:
        return [
            "observations", "segments", "statements", "entities",
            "claims", "facts", "relations", "artifact", "ontology_version", "metadata"
        ]

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    @property
    def relation_count(self) -> int:
        return len(self.relations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact.id,
            "observations": [o.text for o in self.observations],
            "segments": [s.text for s in self.segments],
            "statements": [
                {"subject": s.subject, "predicate": s.predicate, "target": s.target}
                for s in self.statements
            ],
            "entities": [
                {"canonical_name": e.canonical_name, "type": e.entity_type.value}
                for e in self.entities
            ],
            "claims": [
                {"subject": c.subject, "predicate": c.predicate, "target": c.target, "confidence": c.confidence}
                for c in self.claims
            ],
            "facts": [
                {"subject": f.subject, "predicate": f.predicate.value, "object": f.object}
                for f in self.facts
            ],
            "relations": [
                {"subject_id": r.subject_entity_id, "predicate": r.predicate.value, "object_id": r.object_entity_id}
                for r in self.relations
            ],
            "ontology_version": self.ontology_version.value,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Stage 6: MemoryPatch (future - contract interfaces in memory_engine/patch.py)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class MemoryPatch:
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

