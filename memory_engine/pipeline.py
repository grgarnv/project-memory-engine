"""
Compiler Pipeline

    Artifact
      -> observe()             chunk artifact into typed paragraphs
      -> segment()              split each observation by semantic role
      -> extract_statements()   segments -> (subject, predicate, target)
      -> extract_entities()     pull known entities out of segments
      -> extract_claims()       statements -> confidence-scored claims
      -> extract_facts()        claims -> filtered, ontology-normalized facts

    Claim and Fact are deliberately separate: a Claim is anything the
    artifact asserts (may be wrong, vague, or hedged); a Fact is a Claim
    FactPass has accepted as structured knowledge. See extract_facts()
    below for the promotion rule.

Every stage is a plain function: a list in, a list out. There are no
per-stage classes and no hidden call order - `MemoryCompiler.compile()`
below is the entire pipeline, and it is meant to be read top to bottom.
"""
import re

from memory_engine.ir import (
    Artifact,
    Observation,
    Segment,
    SegmentKind,
    Statement,
    Entity,
    Fact,
    Claim,
    Relation,
    CompiledArtifact,
)
from memory_engine.ontology import EntityType, OntologyRegistry, default_ontology_registry
from memory_engine.extractors import (
    StatementExtractor,
    FactExtractor,
    RuleBasedStatementExtractor,
    RuleBasedFactExtractor,
    EntityRecognizer,
    GeneralEntityRecognizer,
    EntityResolver,
    DeterministicEntityResolver,
    RelationExtractor,
    RuleBasedRelationExtractor,
    ResolvedFact,
)

# ---------------------------------------------------------------------------
# Stage 1: Observation
# ---------------------------------------------------------------------------

def observe(artifact: Artifact) -> list[Observation]:
    """Chunk artifact text into paragraphs and tag each with a rough type.

    A ':'-terminated paragraph ("Reason:") is merged with the paragraph
    that follows it, so the label and its body travel together.

    Markdown section headers (e.g. "## Context\nBody text...") are parsed so
    that the section header determines the observation type while the body
    text is preserved. Pure title headers without body text remain "header".
    """
    chunks = [c.strip() for c in artifact.content.split("\n\n") if c.strip()]

    observations = []
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
                lower_header = header_line.lower()
                if "status" in lower_header:
                    obs_type = "status"
                elif "context" in lower_header or "reason" in lower_header:
                    obs_type = "context"
                elif "decision" in lower_header:
                    obs_type = "decision"
                elif "consequence" in lower_header or "trade-off" in lower_header or "tradeoff" in lower_header:
                    obs_type = "consequence"
                else:
                    obs_type = "paragraph"
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

def segment(observations: list[Observation]) -> list[Segment]:
    """Split each observation by semantic role. Standalone title headers carry no claim
    about the change itself, so they're dropped here rather than passed
    downstream as noise."""
    segments = []

    for obs in observations:
        text = obs.text.strip()

        if obs.type == "header":
            continue
        elif obs.type in ("reason", "context") or text.startswith("Reason:"):
            clean_text = text.replace("Reason:", "", 1).strip() if text.startswith("Reason:") else text
            kind = SegmentKind.REASON if obs.type == "reason" else SegmentKind.CONTEXT
            segments.append(
                Segment(
                    kind=kind,
                    text=clean_text,
                    observation_id=obs.id,
                    section_header=obs.section_header,
                    parent_id=obs.id,
                )
            )
        elif obs.type in ("tradeoff", "consequence") or text.startswith("Trade-off:"):
            clean_text = text.replace("Trade-off:", "", 1).strip() if text.startswith("Trade-off:") else text
            kind = SegmentKind.TRADEOFF if obs.type == "tradeoff" else SegmentKind.CONSEQUENCE
            segments.append(
                Segment(
                    kind=kind,
                    text=clean_text,
                    observation_id=obs.id,
                    section_header=obs.section_header,
                    parent_id=obs.id,
                )
            )
        elif obs.type == "decision":
            segments.append(
                Segment(
                    kind=SegmentKind.DECISION,
                    text=text,
                    observation_id=obs.id,
                    section_header=obs.section_header,
                    parent_id=obs.id,
                )
            )
        elif obs.type == "status":
            segments.append(
                Segment(
                    kind=SegmentKind.STATUS,
                    text=text,
                    observation_id=obs.id,
                    section_header=obs.section_header,
                    parent_id=obs.id,
                )
            )
        else:
            segments.append(
                Segment(
                    kind=SegmentKind.DESCRIPTION,
                    text=text,
                    observation_id=obs.id,
                    section_header=obs.section_header,
                    parent_id=obs.id,
                )
            )

    return segments


# ---------------------------------------------------------------------------
# Stage 3: Statement
# ---------------------------------------------------------------------------

def extract_statements(
    segments: list[Segment], extractor: StatementExtractor
) -> list[Statement]:
    statements = []
    for seg in segments:
        statements.extend(extractor.extract(seg))
    return statements


# ---------------------------------------------------------------------------
# Stage 4: Entity
# ---------------------------------------------------------------------------

def extract_entities(
    segments: list[Segment], recognizer: EntityRecognizer | None = None
) -> list[Entity]:

    rec = recognizer or GeneralEntityRecognizer()
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

_HEDGE_WORDS = {
    "should", "might", "may", "could", "probably",
    "likely", "appears", "seems", "possibly", "perhaps",
}
_HEDGED_CONFIDENCE = 0.4
_DEFAULT_CONFIDENCE = 1.0


def _score_confidence(text: str) -> float:
    words = set(re.findall(r"[a-zA-Z']+", text.lower()))
    if words & _HEDGE_WORDS:
        return _HEDGED_CONFIDENCE
    return _DEFAULT_CONFIDENCE


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
# Stage 5b: Fact
# ---------------------------------------------------------------------------

def extract_facts(claims: list[Claim], extractor: FactExtractor) -> list[Fact]:
    facts = []
    for claim in claims:
        facts.extend(extractor.extract(claim))
    return facts


# ---------------------------------------------------------------------------
# Stage 5c: Entity Resolution
# ---------------------------------------------------------------------------

def resolve_entities(
    facts: list[Fact],
    entities: list[Entity],
    claims: list[Claim] | None = None,
    resolver: EntityResolver | None = None,
) -> list[ResolvedFact]:
    res = resolver or DeterministicEntityResolver()
    return res.resolve(facts, entities, claims)


# ---------------------------------------------------------------------------
# Stage 5d: Relation Extraction
# ---------------------------------------------------------------------------

def extract_relations(
    resolved_facts: list[ResolvedFact],
    extractor: RelationExtractor | None = None,
) -> list[Relation]:
    ext = extractor or RuleBasedRelationExtractor()
    return ext.extract(resolved_facts)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class MemoryCompiler:
    """Runs the full Artifact -> Statements/Entities/Facts/Claims/Relations pipeline."""

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
        self.statement_extractor = statement_extractor or RuleBasedStatementExtractor(registry=self.ontology_registry)
        self.fact_extractor = fact_extractor or RuleBasedFactExtractor(registry=self.ontology_registry)
        self.entity_recognizer = entity_recognizer or GeneralEntityRecognizer()
        self.entity_resolver = entity_resolver or DeterministicEntityResolver()
        self.relation_extractor = relation_extractor or RuleBasedRelationExtractor()

    def compile(self, artifact: Artifact) -> CompiledArtifact:
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
        )


