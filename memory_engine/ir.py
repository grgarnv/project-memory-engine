"""
Compiler IR (Intermediate Representation)

Every object the compiler passes between stages lives here, in one file, so
the whole compiler-side data model can be read top to bottom.

    Artifact -> Observation -> Segment -> Statement -> Claim -> Fact
                                   |                             |
                                   +-> Entity ------------------>+-> Relation

Artifact    raw input (a PR, commit, ADR, ...)
Observation artifact chunked into typed paragraphs
Segment     an observation split by semantic role (description/reason/decision/...)
Statement   a segment turned into a (subject, predicate, target) triple
Entity      a named thing (component, feature, capability, ...) pulled from a segment
Claim       something the artifact asserts, scored with a confidence heuristic;
            may be wrong, vague, or hedged - that's fine, it's just a claim
Fact        a Claim FactPass accepted as structured knowledge: confident enough
            AND mapping onto a known ontology Predicate
Relation    Entity --predicate--> Entity, built from Facts whose subject and
            object both resolved to extracted entities

Nothing here is persistent. Persistent memory types live in memory_engine.memory.model;
the compiler must never import them.
"""
from __future__ import annotations

import contextvars
import hashlib
import itertools
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from memory_engine.ontology import EntityType, OntologyVersion, Predicate


# Compiler-local identity.
#
# RFC 003 specifies deterministic local ordinals (obs:0, seg:1) for transient
# compiler nodes, but the IR was using uuid4 - which meant compiling the same
# artifact twice produced different IR and the reproducibility guarantee was
# not actually testable. Inside a `local_id_scope` (entered by
# MemoryCompiler.compile), IDs are ordinals. Outside one - hand-built IR in
# tests, ad-hoc use - they fall back to uuid4.
_local_counters: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "pme_local_counters", default=None
)


class local_id_scope:
    """Makes compiler-local IDs deterministic ordinals for the duration."""

    def __enter__(self) -> "local_id_scope":
        self._token = _local_counters.set({})
        return self

    def __exit__(self, *exc) -> None:
        _local_counters.reset(self._token)


def local_id(prefix: str) -> str:
    counters = _local_counters.get()
    if counters is None:
        return str(uuid.uuid4())
    counter = counters.setdefault(prefix, itertools.count())
    return f"{prefix}:{next(counter)}"


def _uid() -> str:
    return str(uuid.uuid4())


def deterministic_id(scope: str, *components: str) -> str:
    """
    Stable, content-addressed hash ID.

        deterministic_id("artifact", artifact.type.value, artifact.content)
        deterministic_id("entity", canonical_name.lower())

    Entity IDs deliberately hash the NAME ONLY, never the entity type: two
    artifacts that disagree about whether OAuth2 is a FRAMEWORK or a FEATURE
    must still bind to the same entity. See docs/rfcs/RFC_004.
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
    CORRECTION = "correction"


# How much weight an artifact type carries as evidence. An ADR is a deliberate,
# reviewed decision record; a commit message is a side effect of doing the work.
# Used by the linker only - the compiler never reads it.
ARTIFACT_AUTHORITY: dict[ArtifactType, float] = {
    ArtifactType.ADR: 1.0,
    ArtifactType.PR: 0.8,
    ArtifactType.ISSUE: 0.6,
    ArtifactType.COMMIT: 0.5,
    ArtifactType.DOCUMENT: 0.7,
    ArtifactType.SLACK: 0.3,
    ArtifactType.CODE: 0.9,
    # A person saying "that is wrong" outranks every document, but only for
    # retractions. A correction retires a fact; it does not get to make a
    # decision on the project's behalf. See memory_engine/correction.py.
    ArtifactType.CORRECTION: 1.2,
}


@dataclass(slots=True)
class Artifact:
    id: str = field(default_factory=_uid)
    type: ArtifactType = ArtifactType.DOCUMENT
    source: Path | None = None
    content: str = ""
    recorded_at: str = ""  # ISO-8601. When the artifact entered project history.
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def authority(self) -> float:
        return ARTIFACT_AUTHORITY.get(self.type, 0.5)


# ---------------------------------------------------------------------------
# Stage 1: Observation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Observation:
    id: str = field(default_factory=lambda: local_id("obs"))
    text: str = ""
    type: str = "paragraph"  # header | paragraph | reason | tradeoff | decision | status
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
    id: str = field(default_factory=lambda: local_id("seg"))
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
    id: str = field(default_factory=lambda: local_id("stmt"))
    subject: str = ""
    predicate: str = ""
    target: str = ""
    confidence: float = 1.0
    observation_id: str = ""


# ---------------------------------------------------------------------------
# Stage 4: Entity
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Entity:
    id: str = field(default_factory=lambda: local_id("ent"))
    canonical_name: str = ""
    entity_type: EntityType = EntityType.UNKNOWN
    aliases: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 5a: Claim
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Claim:
    id: str = field(default_factory=lambda: local_id("claim"))
    subject: str = ""
    predicate: str = ""
    target: str = ""
    confidence: float = 1.0
    supporting_statements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5b: Fact
# ---------------------------------------------------------------------------

class FactType(Enum):
    RELATIONSHIP = "relationship"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    OBSERVATION = "observation"


@dataclass(slots=True)
class Fact:
    id: str = field(default_factory=lambda: local_id("fact"))
    subject: str = ""
    predicate: Predicate = Predicate.UNKNOWN
    object: str = ""
    fact_type: FactType = FactType.OBSERVATION
    source_claim: str = ""
    confidence: float = 1.0
    supporting_statements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5c: Relation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Relation:
    id: str = field(default_factory=lambda: local_id("rel"))
    subject_entity_id: str = ""
    predicate: Predicate = Predicate.UNKNOWN
    object_entity_id: str = ""
    source_fact_id: str = ""
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Compiler output contract
# ---------------------------------------------------------------------------

@dataclass
class CompiledArtifact:
    """
    Typed container for full compiler output. Dictionary access is preserved
    for the golden-test suite.
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
    compiler_version: str = ""
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
            "claims", "facts", "relations", "artifact",
            "ontology_version", "compiler_version", "metadata",
        ]

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    @property
    def relation_count(self) -> int:
        return len(self.relations)

    def entity_by_id(self, entity_id: str) -> Entity | None:
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        return None

    def claim_by_id(self, claim_id: str) -> Claim | None:
        for claim in self.claims:
            if claim.id == claim_id:
                return claim
        return None

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
                {"subject": c.subject, "predicate": c.predicate,
                 "target": c.target, "confidence": c.confidence}
                for c in self.claims
            ],
            "facts": [
                {"subject": f.subject, "predicate": f.predicate.value, "object": f.object}
                for f in self.facts
            ],
            "relations": [
                {"subject_id": r.subject_entity_id, "predicate": r.predicate.value,
                 "object_id": r.object_entity_id}
                for r in self.relations
            ],
            "ontology_version": self.ontology_version.value,
            "compiler_version": self.compiler_version,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
