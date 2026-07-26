"""
Compiler Pipeline

    Artifact
      -> observe()             chunk artifact into typed paragraphs
      -> segment()              split each observation by semantic role
      -> extract_statements()   segments -> (subject, predicate, target)
      -> extract_entities()     pull known entities out of segments
      -> extract_facts()        statements -> ontology-normalized facts
      -> extract_claims()       statements -> confidence-scored claims

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
)
from memory_engine.ontology import EntityType
from memory_engine.extractors import (
    StatementExtractor,
    FactExtractor,
    RuleBasedStatementExtractor,
    RuleBasedFactExtractor,
)


# ---------------------------------------------------------------------------
# Stage 1: Observation
# ---------------------------------------------------------------------------

def observe(artifact: Artifact) -> list[Observation]:
    """Chunk artifact text into paragraphs and tag each with a rough type.

    A ':'-terminated paragraph ("Reason:") is merged with the paragraph
    that follows it, so the label and its body travel together.
    """
    chunks = [c.strip() for c in artifact.content.split("\n\n") if c.strip()]

    observations = []
    i = 0
    while i < len(chunks):
        text = chunks[i]

        if text.endswith(":") and i + 1 < len(chunks):
            text = text + "\n" + chunks[i + 1]
            i += 1

        if text.startswith("#"):
            obs_type = "header"
        elif text.startswith("Reason:"):
            obs_type = "reason"
        elif text.startswith("Trade-off:"):
            obs_type = "tradeoff"
        else:
            obs_type = "paragraph"

        observations.append(
            Observation(text=text, type=obs_type, artifact_id=artifact.id)
        )
        i += 1

    return observations


# ---------------------------------------------------------------------------
# Stage 2: Segment
# ---------------------------------------------------------------------------

def segment(observations: list[Observation]) -> list[Segment]:
    """Split each observation by semantic role. Headers carry no claim
    about the change itself, so they're dropped here rather than passed
    downstream as noise."""
    segments = []

    for obs in observations:
        text = obs.text.strip()

        if text.startswith("#"):
            continue
        elif text.startswith("Reason:"):
            segments.append(
                Segment(
                    kind=SegmentKind.REASON,
                    text=text.replace("Reason:", "", 1).strip(),
                    observation_id=obs.id,
                )
            )
        elif text.startswith("Trade-off:"):
            segments.append(
                Segment(
                    kind=SegmentKind.TRADEOFF,
                    text=text.replace("Trade-off:", "", 1).strip(),
                    observation_id=obs.id,
                )
            )
        else:
            segments.append(
                Segment(kind=SegmentKind.DESCRIPTION, text=text, observation_id=obs.id)
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

# NOTE: this is a naive fixed-pattern matcher, not a general NER step - it
# will only ever recognize the names listed below. It exists to prove the
# Entity stage out end-to-end; swapping in a real recognizer is a Phase 1
# item (see docs/roadmap.md), same as LLMStatementExtractor.
_KNOWN_ENTITY_PATTERNS = [
    (r"API Gateway", EntityType.COMPONENT),
    (r"JWT validation", EntityType.FEATURE),
    (r"authentication", EntityType.FEATURE),
]


def extract_entities(segments: list[Segment]) -> list[Entity]:
    entities: dict[str, Entity] = {}

    for seg in segments:
        for pattern, entity_type in _KNOWN_ENTITY_PATTERNS:
            for match in re.findall(pattern, seg.text, flags=re.IGNORECASE):
                key = match.lower()
                if key not in entities:
                    entities[key] = Entity(
                        canonical_name=match, entity_type=entity_type, aliases=[match]
                    )

    return list(entities.values())


# ---------------------------------------------------------------------------
# Stage 5a: Fact
# ---------------------------------------------------------------------------

def extract_facts(statements: list[Statement], extractor: FactExtractor) -> list[Fact]:
    facts = []
    for statement in statements:
        facts.extend(extractor.extract(statement))
    return facts


# ---------------------------------------------------------------------------
# Stage 5b: Claim
# ---------------------------------------------------------------------------

def extract_claims(statements: list[Statement]) -> list[Claim]:
    """Wrap each statement as a Claim. Confidence is fixed for now; once
    multiple artifacts can corroborate the same claim, this is where
    confidence would be computed instead of defaulted."""
    return [
        Claim(
            subject=s.subject,
            predicate=s.predicate,
            target=s.target,
            supporting_statements=[s.id],
        )
        for s in statements
    ]


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class MemoryCompiler:
    """Runs the full Artifact -> Statements/Entities/Facts/Claims pipeline."""

    def __init__(
        self,
        statement_extractor: StatementExtractor | None = None,
        fact_extractor: FactExtractor | None = None,
    ):
        self.statement_extractor = statement_extractor or RuleBasedStatementExtractor()
        self.fact_extractor = fact_extractor or RuleBasedFactExtractor()

    def compile(self, artifact: Artifact) -> dict:
        observations = observe(artifact)
        segments = segment(observations)
        statements = extract_statements(segments, self.statement_extractor)
        entities = extract_entities(segments)
        facts = extract_facts(statements, self.fact_extractor)
        claims = extract_claims(statements)

        return {
            "observations": observations,
            "segments": segments,
            "statements": statements,
            "entities": entities,
            "facts": facts,
            "claims": claims,
        }
