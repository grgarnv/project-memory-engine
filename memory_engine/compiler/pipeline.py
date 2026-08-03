"""
Compiler pipeline.

    Artifact
      -> observe()             chunk into typed paragraphs
      -> segment()             split by semantic role
      -> extract_statements()  segments -> (subject, predicate, target)
      -> extract_entities()    segments -> named things
      -> extract_claims()      statements -> confidence-scored assertions
      -> extract_facts()       claims -> ontology-normalized, filtered
      -> resolve_entities()    fact operands -> entity references
      -> extract_relations()   resolved facts -> entity-to-entity edges

Every stage is a plain function: a list in, a list out. `MemoryCompiler.compile()`
is the entire pipeline and nothing runs outside it.

The compiler is stateless and knows nothing about project history. It may import
memory_engine.ir and memory_engine.ontology and nothing else from this package -
enforced by tests/test_import_boundaries.py.
"""
from __future__ import annotations

import re

from memory_engine.compiler.extractors import (
    DeterministicEntityResolver,
    EntityRecognizer,
    EntityResolver,
    FactExtractor,
    RelationExtractor,
    RuleBasedFactExtractor,
    RuleBasedRelationExtractor,
    StatementExtractor,
    default_entity_recognizer,
    default_statement_extractor,
)
from memory_engine.ir import (
    Artifact,
    Claim,
    CompiledArtifact,
    Entity,
    Fact,
    Observation,
    Relation,
    Segment,
    SegmentKind,
    Statement,
    local_id_scope,
)
from memory_engine.ontology import OntologyRegistry, default_ontology_registry

COMPILER_VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Stage 1: Observation
# ---------------------------------------------------------------------------

_HEADER_TYPES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("status",), "status"),
    (("context", "reason", "background", "problem"), "context"),
    (("decision",), "decision"),
    (("consequence", "trade-off", "tradeoff"), "consequence"),
)


_FENCE = re.compile(r"^\s*(?:```|~~~)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _strip_markdown_noise(content: str) -> str:
    """
    Remove fenced code and table rows before chunking.

    A code block is not an assertion about the project, and a table row parsed
    as prose produces one enormous `describes` fact carrying a whole matrix.
    Running against real documentation, unfiltered markdown was the single
    largest source of junk facts.
    """
    lines: list[str] = []
    in_fence = False
    for line in content.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or _TABLE_ROW.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _expand_bullets(chunk: str) -> list[str]:
    """
    One bullet is one assertion. A list collapsed into a single paragraph
    yields one fact for what the author wrote as several.
    """
    lines = chunk.splitlines()
    if not any(_BULLET.match(line) for line in lines):
        return [chunk]

    items: list[str] = []
    current: list[str] = []
    for line in lines:
        if _BULLET.match(line):
            if current:
                items.append(" ".join(current).strip())
            current = [_BULLET.sub("", line).strip()]
        elif line.strip() and current:
            current.append(line.strip())
        elif line.strip():
            items.append(line.strip())
    if current:
        items.append(" ".join(current).strip())
    return [item for item in items if item]


def observe(artifact: Artifact) -> list[Observation]:
    """
    Chunk artifact text into paragraphs and tag each with a rough type.

    A ':'-terminated paragraph ("Reason:") is merged with the paragraph that
    follows, so a label and its body travel together. Markdown section headers
    set the type of the body beneath them; a header with no body stays a header
    and is dropped at the segment stage.
    """
    cleaned = _strip_markdown_noise(artifact.content)
    chunks: list[str] = []
    for block in cleaned.split("\n\n"):
        block = block.strip()
        if block:
            chunks.extend(_expand_bullets(block))

    observations: list[Observation] = []
    current_header = ""
    i = 0
    while i < len(chunks):
        text = chunks[i]

        if text.endswith(":") and i + 1 < len(chunks):
            text = text + "\n" + chunks[i + 1]
            i += 1

        if text.startswith("#"):
            lines = text.split("\n", 1)
            header_line = lines[0].lstrip("#").strip()
            body_text = lines[1].strip() if len(lines) > 1 else ""
            current_header = header_line

            if not body_text:
                obs_type = "header"
            else:
                text = body_text
                lowered = header_line.lower()
                obs_type = "paragraph"
                for keywords, resolved in _HEADER_TYPES:
                    if any(k in lowered for k in keywords):
                        obs_type = resolved
                        break
        elif text.startswith("Reason:"):
            obs_type = "reason"
        elif text.startswith("Trade-off:"):
            obs_type = "tradeoff"
        else:
            obs_type = "paragraph"

        observations.append(
            Observation(
                text=text,
                type=obs_type,
                artifact_id=artifact.id,
                section_header=current_header,
            )
        )
        i += 1

    return observations


# ---------------------------------------------------------------------------
# Stage 2: Segment
# ---------------------------------------------------------------------------

_OBS_TYPE_TO_SEGMENT: dict[str, SegmentKind] = {
    "reason": SegmentKind.REASON,
    "context": SegmentKind.CONTEXT,
    "tradeoff": SegmentKind.TRADEOFF,
    "consequence": SegmentKind.CONSEQUENCE,
    "decision": SegmentKind.DECISION,
    "status": SegmentKind.STATUS,
    "paragraph": SegmentKind.DESCRIPTION,
}

_LABEL_PREFIXES = ("Reason:", "Trade-off:")


def segment(observations: list[Observation]) -> list[Segment]:
    """
    Split each observation by semantic role. Standalone title headers carry no
    claim about the change itself, so they are dropped rather than passed on
    as noise.
    """
    segments: list[Segment] = []

    for obs in observations:
        if obs.type == "header":
            continue

        text = obs.text.strip()
        kind = _OBS_TYPE_TO_SEGMENT.get(obs.type, SegmentKind.DESCRIPTION)

        for prefix in _LABEL_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                kind = (
                    SegmentKind.REASON if prefix == "Reason:" else SegmentKind.TRADEOFF
                )
                break

        segments.append(
            Segment(
                kind=kind,
                text=text,
                observation_id=obs.id,
                section_header=obs.section_header,
                parent_id=obs.id,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# Stage 3-4: Statement, Entity
# ---------------------------------------------------------------------------

def extract_statements(
    segments: list[Segment], extractor: StatementExtractor
) -> list[Statement]:
    statements: list[Statement] = []
    for seg in segments:
        statements.extend(extractor.extract(seg))
    return statements


def extract_entities(
    segments: list[Segment], recognizer: EntityRecognizer | None = None
) -> list[Entity]:
    rec = recognizer or default_entity_recognizer()
    entities: dict[str, Entity] = {}
    for seg in segments:
        for entity in rec.recognize(seg.text):
            key = entity.canonical_name.lower()
            if key not in entities:
                entities[key] = entity
    return list(entities.values())


# ---------------------------------------------------------------------------
# Stage 5a: Claim
# ---------------------------------------------------------------------------

_HEDGE_WORDS = frozenset({
    "should", "might", "may", "could", "probably",
    "likely", "appears", "seems", "possibly", "perhaps",
})
_HEDGED_CONFIDENCE = 0.4
_DEFAULT_CONFIDENCE = 1.0


def _score_confidence(text: str) -> float:
    """
    Hedge-word heuristic. Placeholder: it measures assertiveness of phrasing,
    not likelihood of truth. Named and isolated so replacing it touches one
    function.
    """
    words = set(re.findall(r"[a-zA-Z']+", text.lower()))
    return _HEDGED_CONFIDENCE if words & _HEDGE_WORDS else _DEFAULT_CONFIDENCE


def extract_claims(statements: list[Statement]) -> list[Claim]:
    return [
        Claim(
            subject=s.subject,
            predicate=s.predicate,
            target=s.target,
            confidence=_score_confidence(s.target),
            supporting_statements=[s.id],
        )
        for s in statements
    ]


# ---------------------------------------------------------------------------
# Stage 5b-5d: Fact, resolution, Relation
# ---------------------------------------------------------------------------

def extract_facts(claims: list[Claim], extractor: FactExtractor) -> list[Fact]:
    facts: list[Fact] = []
    for claim in claims:
        facts.extend(extractor.extract(claim))
    return facts


def resolve_entities(
    facts: list[Fact],
    entities: list[Entity],
    claims: list[Claim] | None = None,
    resolver: EntityResolver | None = None,
):
    return (resolver or DeterministicEntityResolver()).resolve(facts, entities, claims)


def extract_relations(resolved_facts, extractor: RelationExtractor | None = None) -> list[Relation]:
    return (extractor or RuleBasedRelationExtractor()).extract(resolved_facts)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class MemoryCompiler:
    """
    Stateless single-artifact knowledge extractor.

    Determinism guarantee: identical output for identical
    (artifact content, compiler version, ontology version, extractor config).
    Not an absolute guarantee - see RFC 004. `CompiledArtifact` records the
    compiler and ontology version so a stored compilation can be re-derived.
    """

    def __init__(
        self,
        statement_extractor: StatementExtractor | None = None,
        fact_extractor: FactExtractor | None = None,
        entity_recognizer: EntityRecognizer | None = None,
        entity_resolver: EntityResolver | None = None,
        relation_extractor: RelationExtractor | None = None,
        ontology_registry: OntologyRegistry | None = None,
    ):
        self.ontology_registry = ontology_registry or default_ontology_registry()
        self.statement_extractor = statement_extractor or default_statement_extractor(
            registry=self.ontology_registry
        )
        self.fact_extractor = fact_extractor or RuleBasedFactExtractor(
            registry=self.ontology_registry
        )
        self.entity_recognizer = entity_recognizer or default_entity_recognizer()
        self.entity_resolver = entity_resolver or DeterministicEntityResolver()
        self.relation_extractor = relation_extractor or RuleBasedRelationExtractor()

    def compile(self, artifact: Artifact) -> CompiledArtifact:
        with local_id_scope():
            return self._compile(artifact)

    def _compile(self, artifact: Artifact) -> CompiledArtifact:
        observations = observe(artifact)
        segments = segment(observations)
        statements = extract_statements(segments, self.statement_extractor)
        entities = extract_entities(segments, self.entity_recognizer)
        claims = extract_claims(statements)
        facts = extract_facts(claims, self.fact_extractor)
        resolved_facts = resolve_entities(facts, entities, claims, self.entity_resolver)
        relations = extract_relations(resolved_facts, self.relation_extractor)

        return CompiledArtifact(
            artifact=artifact,
            observations=observations,
            segments=segments,
            statements=statements,
            entities=entities,
            claims=claims,
            facts=facts,
            relations=relations,
            ontology_version=self.ontology_registry.version,
            compiler_version=COMPILER_VERSION,
        )
